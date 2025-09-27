"""Driver discovery system using entry points."""

import importlib
import logging
from importlib.metadata import entry_points
from typing import Dict, List

from ..protocol import Catalog

logger = logging.getLogger(__name__)


def discover_available_drivers() -> Dict[str, dict]:
    """
    Discover and validate all available drivers via entry points.

    Returns a dictionary mapping driver names to their validated info.
    Only includes drivers that can be imported and implement the Catalog protocol.
    """
    driver_info = {}

    try:
        eps = entry_points(group="hamrss.drivers")

        for ep in eps:
            try:
                # Load the module
                module = importlib.import_module(ep.value)

                # Check if module has a Catalog class
                if not hasattr(module, "Catalog"):
                    logger.warning(f"Driver {ep.name} missing Catalog class")
                    continue

                catalog_class = getattr(module, "Catalog")

                # Create instance and validate using isinstance with the protocol
                try:
                    temp_instance = catalog_class(playwright_server=None)

                    if isinstance(temp_instance, Catalog):
                        # Get categories if possible
                        categories = []
                        try:
                            categories = temp_instance.get_categories()
                        except Exception:
                            # If we can't get categories, that's ok
                            pass

                        driver_info[ep.name] = {
                            "name": ep.name,
                            "module": ep.value,
                            "catalog_class": catalog_class,
                            "categories": categories,
                            "entry_point": ep,
                        }
                    else:
                        logger.warning(
                            f"Driver {ep.name} Catalog class does not implement the required protocol"
                        )

                except Exception as e:
                    logger.warning(f"Could not instantiate driver {ep.name}: {e}")

            except ImportError as e:
                logger.warning(f"Could not import driver {ep.name} ({ep.value}): {e}")
            except Exception as e:
                logger.warning(f"Error loading driver {ep.name}: {e}")

    except Exception as e:
        logger.warning(f"Error discovering drivers via entry points: {e}")

    return driver_info


def get_available_driver_modules() -> List[str]:
    """
    Get list of available and valid driver module names.

    Returns only drivers that can be imported and implement the Catalog protocol.
    """
    driver_info = discover_available_drivers()
    return [info["module"] for info in driver_info.values()]


def get_available_driver_names() -> List[str]:
    """
    Get list of available driver names (entry point names).

    Returns only drivers that can be imported and implement the Catalog protocol.
    """
    driver_info = discover_available_drivers()
    return list(driver_info.keys())
