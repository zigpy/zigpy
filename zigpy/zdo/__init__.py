from __future__ import annotations

import zigpy.types as t

from . import commands

ZDO_ENDPOINT = 0


def broadcast(
    app,
    command: commands.ZDOPayload,
    grpid,
    radius,
    *,
    broadcast_address=t.BroadcastAddress.RX_ON_WHEN_IDLE,
):
    sequence = app.get_sequence()
    data = commands.ZDOCommand(
        command_id=command.command_id, tsn=t.uint8_t(sequence), command=command
    ).serialize()

    return app.broadcast(
        profile=0x0000,
        cluster=command.command_id,
        src_ep=ZDO_ENDPOINT,
        dst_ep=ZDO_ENDPOINT,
        grpid=grpid,
        radius=radius,
        sequence=sequence,
        data=data,
        broadcast_address=broadcast_address,
    )
