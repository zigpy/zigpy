import datetime

import pydantic

import zigpy.state as state


class NetworkBackup(pydantic.BaseModel):
    backup_time: datetime.datetime
    network_info: state.NetworkInfo
    node_info: state.NodeInfo

    def compatible_with(
        self, network_info: state.NetworkInfo, node_info: state.NodeInfo
    ) -> bool:
        """
        Checks if this network backup uses settings compatible with the provided ones.
        """

        return (
            self.node_info == node_info
            and self.network_info.extended_pan_id == network_info.extended_pan_id
            and self.network_info.pan_id == network_info.pan_id
            and self.network_info.nwk_update_id == network_info.nwk_update_id
            and self.network_info.nwk_manager_id == network_info.nwk_manager_id
            and self.network_info.channel == network_info.channel
            and self.network_info.security_level == network_info.security_level
            # The frame counters will not match up so we only worry about the key
            and self.network_info.tc_link_key.key == network_info.tc_link_key.key
            and self.network_info.network_key.key == network_info.network_key.key
        )
