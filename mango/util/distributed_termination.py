"""Module, which implements a simple termination detection for negotiations. Here Huangs
detection algorithm is used (10.1109/ICDCS.1989.37933).

It requires the distributed negotiation to have some kind of controller agent. In general
this can often be the initiator.

Roles:
* :class:`NegotiationTerminationRole`: role for the participants, hooks into sending messages,
                                       adding the weight value

Messages:
* :class:`TerminationMessage`: this message will be sent to the controller, when an agent
considers itself as inactive.
"""

import asyncio
from collections.abc import Callable
from fractions import Fraction
from typing import Any
from uuid import UUID

from mango import AgentAddress, Role, sender_addr
from mango.messages.codecs import json_serializable


@json_serializable
class TerminationMessage:
    """Message for sending the remaining weight to the controller"""

    def __init__(
        self, weight: Fraction, coalition_id: UUID, negotiation_id: UUID
    ) -> None:
        self._weight = weight
        self._coalition_id = coalition_id
        self._negotiation_id = negotiation_id

    @property
    def weight(self) -> Fraction:
        """Return the remaining weight

        :return: remaining weight
        """
        return self._weight

    @property
    def coalition_id(self) -> UUID:
        """Return the coalition id the negotiation is referring to

        :return: the coalition id
        """
        return self._coalition_id

    @property
    def negotiation_id(self) -> UUID:
        """Return the negotiation id

        :return: the negotiation id
        """
        return self._negotiation_id


@json_serializable
class InformAboutTerminationMessage:
    """
    Message that informs an agent that a negotiation should be stopped.
    """

    def __init__(self, negotiation_id: UUID, participants: list[AgentAddress]) -> None:
        self._negotiation_id = negotiation_id
        self._participants = participants

    @property
    def negotiation_id(self) -> UUID:
        """Return the negotiation id

        :return: the negotiation id
        """
        return self._negotiation_id

    @property
    def participants(self) -> list[AgentAddress]:
        """Return the list of participants as AgentAddress

        :return: the participants
        """
        return self._participants


class NegotiationTerminationParticipantRole(Role):
    """Role for negotiation participants. Will add the weight attribute to every
    coalition related message send.
    """

    def __init__(
        self,
        controller_agent: AgentAddress,
    ):
        super().__init__()
        self.controller_agent = controller_agent
        self._weight_map: dict[float, Fraction] = {}
        self._termination_check_tasks: dict[float, asyncio.Task] = {}

    def setup(self):
        super().setup()
        self.context.subscribe_send(self, self.on_send)

        self.context.subscribe_message(
            self,
            self.handle_neg_msg,
            lambda c, _: isinstance(c, dict) and "negotiation_id" in c,
        )

    def on_send(
        self,
        content,
        receiver_addr: AgentAddress,
        additional_arguments: dict,
    ):
        """Add the weight to every coalition related message

        :param content: content of the message
        :param receiver_addr: AgentAddress
        :param receiver_id: id of the receiver. Defaults to None.
        :param kwargs: additional parameters
        """
        if additional_arguments.get("negotiation_id"):
            # if there is no negotitation give, use the time
            neg_id = additional_arguments.get("negotiation_id", self.context.current_timestamp)
            if neg_id not in self._weight_map:
                raise ValueError(
                    "negotiation id not set in additional arguments"
                )
                self._weight_map[neg_id] = Fraction(0, 1)
            additional_arguments["negotiation_id"] = neg_id
            if not additional_arguments.get("message_weight"):
                additional_arguments["weight"] = self._weight_map[neg_id] /2
            # we keep the other fraction
            self._weight_map[neg_id] /= 2

    def handle_neg_msg(self, content: dict[str, Any], meta: dict[str, Any]) -> None:
        """Check whether a coalition related message has been received and manipulate the internal
        weight accordingly. Setup a conditional task that checks for termination.

        :param content: the incoming neogtiation message
        :param _: the meta data
        """
        neg_id = meta["negotiation_id"]
        weight = meta["message_weight"]
        if neg_id in self._weight_map:
            self._weight_map[neg_id] += weight
        else:
            self._weight_map[neg_id] = weight

        def _check_weight_condition() -> bool:
            """
            Function that checks whether the negotiation has 'probably' terminated.
            :return: boolean
            """
            return (
                not self._negotiation_model.by_id(
                    negotiation_id=neg_id
                ).active
                and self._weight_map[neg_id] == 0
            )

        if (
            neg_id not in self._termination_check_tasks
            or self._termination_check_tasks[neg_id].done()
        ):
            # create a new conditional task that checks for termination
            self._termination_check_tasks[neg_id] = (
                self.context.schedule_conditional_task(
                    self._send_weight(self.controller_agent, meta),
                    condition_func=_check_weight_condition,
                )
            )

    async def _send_weight(self, termination_detector: AgentAddress, meta):
        """
        Sends the current weight to the termination controller
        :param termination_detector: AgentAddress of the termination detector that should receive the
        weight message
        :param content: The NeogotiationMessage

        """
        # store weight
        neg_id = meta["negotiation_id"]
        coalition_id = meta["coalition_id"]
        current_weight = self._weight_map[neg_id]
        # reset weight
        self._weight_map[neg_id] = Fraction(0, 1)
        # Send weight
        await self.context.send_message(
            content=TerminationMessage(
                current_weight, coalition_id, neg_id
            ),
            receiver_addr=termination_detector,
        )


class NegotiationTerminationDetectorRole(Role):
    """ """

    def __init__(
        self,
        on_termination: Callable = None,
        aggregator_addr: AgentAddress = None,
    ):
        super().__init__()
        self._weight_map: dict[UUID, Fraction] = {}
        self._participant_map: dict[UUID, AgentAddress] = {}
        self._on_termination = (
            on_termination if on_termination is not None else self._send_stop_and_inform
        )
        self._aggregator_addr = aggregator_addr

    def setup(self):
        super().setup()
        self.context.subscribe_message(
            self, self.handle_term_msg, lambda c, _: isinstance(c, TerminationMessage)
        )
        if self._aggregator_addr is None:
            self._aggregator_addr = self.context.addr

    async def _send_stop_and_inform(self, negotiation_id):
        # send stopNegotiationMessage first
        for agent_addr in self._participant_map[negotiation_id]:
            await self.context.send_message(
                content=negotiation_id,
                receiver_addr=agent_addr,
            )

        # now send message to aggregator
        if self._aggregator_addr is not None:
            await self.context.send_message(
                content=InformAboutTerminationMessage(
                    negotiation_id=negotiation_id,
                    participants=list(self._participant_map[negotiation_id]),
                ),
                receiver_addr=self._aggregator_addr,
            )

    def handle_term_msg(
        self, content: TerminationMessage, meta: dict[str, Any]
    ) -> None:
        """Handle the termination message.

        :param content: the message
        :param meta: meta data
        """
        neg_id = meta["negotiation_id"]
        if "sender_addr" in meta and "sender_id" in meta:
            if neg_id not in self._participant_map:
                self._participant_map[neg_id] = set()
            self._participant_map[neg_id].add(sender_addr(meta))

        if neg_id not in self._weight_map:
            self._weight_map[neg_id] = content.weight
        else:
            self._weight_map[neg_id] += content.weight

        if self._weight_map[neg_id] == 1:
            self.context.schedule_instant_task(self._on_termination(neg_id))
