from typing import List

from remnawave.models import NodeResponseDto, UpdateHostRequestDto

from remnawave import RemnawaveSDK
from ..utils.logger import get_logger


class RemnawaveClient:
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.logger = get_logger(__name__)
        self.sdk = RemnawaveSDK(base_url=self.api_url, token=self.api_key)

    async def get_nodes(self) -> List[NodeResponseDto]:
        try:
            self.logger.info(f"Fetching nodes from {self.api_url}")

            response = await self.sdk.nodes.get_all_nodes() # GetAllNodesResponseDto
            nodes_list = response.root if hasattr(response, "root") else []

            self.logger.info(f"Successfully fetched {len(nodes_list)} nodes")
            return nodes_list
        except Exception as e:
            self.logger.error(f"Error fetching nodes: {e}")
            raise

    async def get_hosts(self) -> list:
        try:
            response = await self.sdk.hosts.get_all_hosts()
            return response.root if hasattr(response, "root") else []
        except Exception as e:
            self.logger.error(f"Error fetching hosts: {e}")
            raise

    async def set_host_disabled(self, uuid: str, is_disabled: bool) -> None:
        await self.sdk.hosts.update_host(
            body=UpdateHostRequestDto(uuid=uuid, is_disabled=is_disabled)
        )

    @staticmethod
    def is_node_connected(node: NodeResponseDto) -> bool:
        return node.is_connected

    @staticmethod
    def is_node_disabled(node: NodeResponseDto) -> bool:
        return node.is_disabled

    @staticmethod
    def is_node_healthy(node: NodeResponseDto) -> bool:
        return RemnawaveClient.is_node_connected(node) and not RemnawaveClient.is_node_disabled(node)
