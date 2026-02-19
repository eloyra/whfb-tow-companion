from fastapi import APIRouter, Query

router = APIRouter()


@router.get("/nodes")
async def get_nodes(
    node_type: str | None = Query(None),
    limit: int = Query(100, le=1000),
) -> dict:
    # TODO: return nodes from graph for UI visualisation
    raise NotImplementedError


@router.get("/subgraph/{node_id}")
async def get_subgraph(node_id: str, depth: int = Query(2, le=4)) -> dict:
    # TODO: return neighbourhood of a node for UI visualisation
    raise NotImplementedError
