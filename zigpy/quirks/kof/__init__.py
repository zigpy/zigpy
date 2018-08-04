"""
This module handles quirks of the King of Fans MR101Z ceiling fan receiver.

The King of Fans ceiling fan receiver does not generate default replies. This
module overrides all server commands that do not have a mandatory reply to not
 expect replies at all.
"""
from zigpy.quirks import CustomDevice, CustomCluster
from zigpy.zcl.clusters.general import Basic, Identify, Groups, Scenes, OnOff, LevelControl, Ota
from zigpy.zcl.clusters.hvac import Fan


class NoReplyMixin(object):
    """
    A simple mixin that allows a cluster to have configureable list of command
    ids that do not generate an explicit reply.
    """
    void_input_commands = []

    def command(self, command, *args, manufacturer=None, expect_reply=None):
        """
        Overrides Cluster#command to configure expect_reply behavior based on
        void_input_commands. Note that this method changes the default value of
        expect_reply to None. This allows the caller to explicitly force
        expect_reply to true.
        """
        if expect_reply is None:
            expect_reply = command not in self.void_input_commands

        return super(NoReplyMixin, self).command(command, *args, manufacturer=manufacturer, expect_reply=expect_reply)


class KofBasic(NoReplyMixin, CustomCluster, Basic):
    void_input_commands = [0x00]


class KofIdentify(NoReplyMixin, CustomCluster, Identify):
    # Identify, Trigger Effect
    void_input_commands = [0x00, 0x40]


class KofGroups(NoReplyMixin, CustomCluster, Groups):
    # Remove All Groups, Add Group If Identifying
    void_input_commands = [0x04, 0x05]


class KofScenes(NoReplyMixin, CustomCluster, Scenes):
    # Recall Scene
    void_input_commands = [0x05]


class KofOnOff(NoReplyMixin, CustomCluster, OnOff):
    # All
    void_input_commands = [0x00, 0x01, 0x02, 0x40, 0x41, 0x42]


class KofLevelControl(NoReplyMixin, CustomCluster, LevelControl):
    # All
    void_input_commands = [0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07]


class CeilingFan(CustomDevice):
    signature = {
        1: {
            'profile_id': 0x0104,
            'device_type': 14,
            'input_clusters': [
                Basic.cluster_id,
                Identify.cluster_id,
                Groups.cluster_id,
                Scenes.cluster_id,
                OnOff.cluster_id,
                LevelControl.cluster_id,
                Fan.cluster_id,
            ],
            'output_clusters': [
                Identify.cluster_id,
                Ota.cluster_id,
            ],
        },
    }

    replacement = {
        'endpoints': {
            1: {
                'input_clusters': [
                    KofBasic,
                    KofIdentify,
                    KofGroups,
                    KofScenes,
                    KofOnOff,
                    KofLevelControl,
                    Fan,
                ],
                'output_clusters': [
                    Identify,
                    Ota,
                ]
            }
        },
    }
