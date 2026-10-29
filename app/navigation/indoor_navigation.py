from collections import deque
from typing import Dict, List, Optional


# Example map for testing only.
# Replace these connections with your actual indoor layout.
INDOOR_MAP = {
    "entrance": {
        "name": "Entrance",
        "neighbors": ["corridor"],
    },
    "corridor": {
        "name": "Main corridor",
        "neighbors": ["entrance", "dining_room", "bedroom"],
    },
    "dining_room": {
        "name": "Dining room",
        "neighbors": ["corridor"],
    },
    "bedroom": {
        "name": "Bedroom",
        "neighbors": ["corridor"],
    },
}


def validate_indoor_map(map_graph: Dict[str, dict]) -> None:
    """Validates the structural integrity of an indoor graph.

    Checks:
    - Each node is defined with a display name and neighbors list.
    - All neighbor references exist within the map keys.
    - Consistency of bidirectional edges between adjacent locations.

    Raises:
        ValueError: If graph definition contains invalid or orphaned references.
    """
    if not map_graph:
        raise ValueError("Indoor map definition cannot be empty.")

    for node_id, data in map_graph.items():
        if "name" not in data or not isinstance(data["name"], str):
            raise ValueError(f"Node '{node_id}' missing a valid string 'name' field.")
        if "neighbors" not in data or not isinstance(data["neighbors"], (list, set)):
            raise ValueError(f"Node '{node_id}' missing a valid 'neighbors' list.")

        for neighbor in data["neighbors"]:
            if neighbor not in map_graph:
                raise ValueError(
                    f"Node '{node_id}' references non-existent neighbor '{neighbor}'."
                )
            # Check bidirectional symmetry
            if node_id not in map_graph[neighbor].get("neighbors", []):
                raise ValueError(
                    f"Asymmetric connection: '{node_id}' lists '{neighbor}' as a neighbor, "
                    f"but '{neighbor}' does not link back to '{node_id}'."
                )


def normalize_location(location: str, map_graph: Optional[Dict[str, dict]] = None) -> str:
    """Normalizes user or API input to a valid indoor map key.

    Handles:
    - Whitespace trimming and case-insensitivity.
    - Conversion of spaces/hyphens to underscores.
    - Matching against display names (e.g. 'Main corridor' -> 'corridor').

    Returns:
        str: Canonical location key in the map graph.

    Raises:
        ValueError: If the location cannot be resolved to a known landmark.
    """
    if map_graph is None:
        map_graph = INDOOR_MAP

    if not location or not isinstance(location, str):
        valid_keys = ", ".join(sorted(map_graph.keys()))
        raise ValueError(
            f"Invalid location input. Expected a non-empty string. Supported: {valid_keys}"
        )

    raw_stripped = location.strip()
    if raw_stripped in map_graph:
        return raw_stripped

    cleaned = raw_stripped.lower()
    candidate = cleaned.replace(" ", "_").replace("-", "_")

    if candidate in map_graph:
        return candidate

    # Match case-insensitively against map keys
    for key in map_graph:
        if key.lower() == cleaned or key.lower() == candidate:
            return key

    # Match against display names
    for key, data in map_graph.items():
        if data.get("name", "").strip().lower() == cleaned:
            return key

    valid_keys = ", ".join(sorted(map_graph.keys()))
    raise ValueError(
        f"Unknown indoor location: '{location.strip()}'. Supported: {valid_keys}"
    )


def generate_route_instructions(locations: List[str]) -> List[str]:
    """Generates clear, sequential, non-technical verbal instructions for a route.

    Does not invent directions (left/right/angles) absent from map metadata.

    Args:
        locations: Ordered list of display names along the route path.

    Returns:
        List[str]: Spoken navigation instructions for each transition.
    """
    if not locations:
        return []

    if len(locations) == 1:
        return [f"You are already at your destination: {locations[0]}."]

    instructions = [f"{locations[0]} identified."]

    if len(locations) == 2:
        instructions.append(f"Follow the mapped route to {locations[1]}.")
        instructions.append(f"The route has reached the {locations[1]} landmark.")
        return instructions

    # For routes with 3 or more nodes:
    # First transition
    instructions.append(f"Follow the mapped route to {locations[1]}.")

    # Intermediate transitions
    for loc in locations[2:-1]:
        instructions.append(f"Proceed along the route through {loc}.")

    # Destination transition
    instructions.append(f"Continue toward {locations[-1]}.")
    instructions.append(f"The route has reached the {locations[-1]} landmark.")

    return instructions


def find_indoor_route(
    start: str,
    destination: str,
    map_graph: Optional[Dict[str, dict]] = None,
) -> dict:
    """Find the shortest route through the configured indoor map using Breadth-First Search (BFS).

    Args:
        start: Starting location key or display name.
        destination: Target destination key or display name.
        map_graph: Optional custom indoor graph (defaults to INDOOR_MAP).

    Returns:
        dict containing:
            - start: Display name of starting point
            - destination: Display name of destination
            - route: Ordered list of display names along shortest path
            - route_nodes: Ordered list of canonical node IDs
            - instructions: Ordered list of spoken navigation steps
            - total_steps: Number of edge transitions (0 if already at destination)
            - status: 'success'

    Raises:
        ValueError: If start or destination are invalid, or no walkable route exists.
    """
    if map_graph is None:
        map_graph = INDOOR_MAP

    validate_indoor_map(map_graph)

    start_key = normalize_location(start, map_graph)
    dest_key = normalize_location(destination, map_graph)

    start_name = map_graph[start_key]["name"]
    dest_name = map_graph[dest_key]["name"]

    if start_key == dest_key:
        return {
            "start": start_name,
            "destination": dest_name,
            "route": [start_name],
            "route_nodes": [start_key],
            "instructions": [f"You are already at your destination: {start_name}."],
            "total_steps": 0,
            "status": "success",
        }

    queue = deque([[start_key]])
    visited = {start_key}

    while queue:
        path = queue.popleft()
        current = path[-1]

        if current == dest_key:
            locations = [map_graph[node]["name"] for node in path]
            instructions = generate_route_instructions(locations)

            return {
                "start": start_name,
                "destination": dest_name,
                "route": locations,
                "route_nodes": path,
                "instructions": instructions,
                "total_steps": len(path) - 1,
                "status": "success",
            }

        for neighbor in map_graph[current].get("neighbors", []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(path + [neighbor])

    raise ValueError(f"No walkable route connects {start_name} to {dest_name}.")
