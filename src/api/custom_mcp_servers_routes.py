"""
┌──────────────────────────────────────────────────────────────────────────────┐
│ @author: Davidson Gomes                                                      │
│ @file: custom_mcp_servers_routes.py                                         │
│ Developed by: Davidson Gomes                                                 │
│ Creation date: January 14, 2025                                              │
│ Contact: contato@evolution-api.com                                           │
├──────────────────────────────────────────────────────────────────────────────┤
│ @copyright © Evolution API 2025. All rights reserved.                        │
│ Licensed under the Apache License, Version 2.0                               │
│                                                                              │
│ You may not use this file except in compliance with the License.             │
│ You may obtain a copy of the License at                                      │
│                                                                              │
│    http://www.apache.org/licenses/LICENSE-2.0                                │
│                                                                              │
│ Unless required by applicable law or agreed to in writing, software          │
│ distributed under the License is distributed on an "AS IS" BASIS,            │
│ WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.     │
│ See the License for the specific language governing permissions and          │
│ limitations under the License.                                               │
├──────────────────────────────────────────────────────────────────────────────┤
│ @important                                                                   │
│ For any future changes to the code in this file, it is recommended to        │
│ include, together with the modification, the information of the developer    │
│ who changed it and the date of modification.                                 │
└──────────────────────────────────────────────────────────────────────────────┘
"""

from datetime import datetime, timezone
from pydantic import Field
from typing import List
from fastapi import APIRouter, status, Depends, Request
from src.schemas.schemas import (
    CustomMCPDiscoverToolsCreate,
    CustomMCPDiscoverToolsResponse
)
from src.services import custom_mcp_server_service
from src.api.dependencies import get_current_user
from src.middleware.permissions import RequirePermission
from src.utils.response import success_response, error_response, map_status_to_error_code, MetaInfo
from src.schemas.responses import SuccessResponse, ErrorResponse
from src.schemas.response_models import DiscoverToolsResponse
import logging

logger = logging.getLogger(__name__)

class CustomDiscoverToolsResponse(SuccessResponse[DiscoverToolsResponse]):
    tools: List[dict] = Field(..., description="Duplicate of tools at root level for Go core compatibility")

router = APIRouter(
    prefix="/custom-mcp-servers",
    tags=["custom-mcp-servers"],
)

@router.post(
    "/discover-tools",
    response_model=CustomDiscoverToolsResponse,
    responses={
        200: {"description": "Tools discovered successfully"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def create_discover_tools(
    request: Request,
    discover_tools: CustomMCPDiscoverToolsCreate,
    permission: None = Depends(RequirePermission("ai_custom_mcp_servers", "discover")),
    _: dict = Depends(get_current_user),
):
    """Discover tools from a custom MCP server"""
    
    logger.info(f"🔍 Discover tools endpoint called for URL: {discover_tools.url}")
    
    try:
        result = await custom_mcp_server_service.discover_custom_mcp_server_tools(
            discover_tools
        )
        
        if result.get("success") is False:
            error_msg = result.get("error", "Unknown error")
            logger.error(f"Error discovering tools: {error_msg}")
            meta_info = MetaInfo(timestamp=datetime.now(timezone.utc).isoformat())
            return {
                "success": False,
                "data": {"tools": []},
                "meta": meta_info,
                "tools": [],
                "message": f"Error: {error_msg}"
            }
        
        discovered_tools = result.get("tools", [])
        logger.info(f"Discovered {len(discovered_tools)} tools from custom MCP server")
        
        meta_info = MetaInfo(timestamp=datetime.now(timezone.utc).isoformat())
        return {
            "success": True,
            "data": {"tools": discovered_tools},
            "meta": meta_info,
            "tools": discovered_tools,
            "message": f"Discovered {len(discovered_tools)} tools from custom MCP server"
        }
        
    except Exception as e:
        logger.error(f"Unexpected error discovering tools: {str(e)}")
        return error_response(
            request=request,
            code=map_status_to_error_code(status.HTTP_500_INTERNAL_SERVER_ERROR),
            message=f"Error discovering tools: {str(e)}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )