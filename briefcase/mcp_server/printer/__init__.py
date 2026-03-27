"""Printer interface module for BriefCase."""

from typing import Dict, Any
from .network_printer import NetworkPrinter


def get_printer(config: Dict[str, Any]):
    """Returns appropriate printer interface based on config.

    Args:
        config: Printer config dict with type, host, port keys.

    Returns:
        Configured printer object ready for printing.
    """
    printer_type = config.get("type", "network")

    if printer_type == "network":
        host = config.get("host")
        port = config.get("port", 9100)
        if not host:
            raise ValueError("Network printer requires host in config")
        return NetworkPrinter(host, port)
    else:
        raise ValueError(f"Unknown printer type: {printer_type}")


__all__ = ["get_printer"]
