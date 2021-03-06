import copy
import logging
from typing import Optional

import requests

import great_expectations.exceptions as ge_exceptions
from great_expectations.core.batch import BatchRequest
from great_expectations.core.util import nested_update
from great_expectations.data_context.types.base import CheckpointConfig

logger = logging.getLogger(__name__)


def send_slack_notification(query, slack_webhook):
    session = requests.Session()

    try:
        response = session.post(url=slack_webhook, json=query)
    except requests.ConnectionError:
        logger.warning(
            "Failed to connect to Slack webhook at {url} "
            "after {max_retries} retries.".format(url=slack_webhook, max_retries=10)
        )
    except Exception as e:
        logger.error(str(e))
    else:
        if response.status_code != 200:
            logger.warning(
                "Request to Slack webhook at {url} "
                "returned error {status_code}: {text}".format(
                    url=slack_webhook,
                    status_code=response.status_code,
                    text=response.text,
                )
            )
        else:
            return "Slack notification succeeded."


def send_opsgenie_alert(query, suite_name, settings):
    """Creates an alert in Opsgenie."""
    if settings["region"] != None:
        url = "https://api.{region}.opsgenie.com/v2/alerts".format(
            region=settings["region"]
        )  # accomodate for Europeans
    else:
        url = "https://api.opsgenie.com/v2/alerts"

    headers = {
        "Authorization": "GenieKey {api_key}".format(api_key=settings["api_key"])
    }
    payload = {
        "message": "Great Expectations suite {suite_name} failed".format(
            suite_name=suite_name
        ),
        "description": query,
        "priority": settings["priority"],  # allow this to be modified in settings
    }

    session = requests.Session()

    try:
        response = session.post(url, headers=headers, json=payload)
    except requests.ConnectionError:
        logger.warning("Failed to connect to Opsgenie")
    except Exception as e:
        logger.error(str(e))
    else:
        if response.status_code != 202:
            logger.warning(
                "Request to Opsgenie API at {url} "
                "returned error {status_code}: {text}".format(
                    url=url,
                    status_code=response.status_code,
                    text=response.text,
                )
            )
        else:
            return "success"
    return "error"


def send_microsoft_teams_notifications(query, microsoft_teams_webhook):
    session = requests.Session()
    try:
        response = session.post(url=microsoft_teams_webhook, json=query)
    except requests.ConnectionError:
        logger.warning(
            "Failed to connect to Microsoft Teams webhook at {url} "
            "after {max_retries} retries.".format(
                url=microsoft_teams_webhook, max_retries=10
            )
        )
    except Exception as e:
        logger.error(str(e))
    else:
        if response.status_code != 200:
            logger.warning(
                "Request to Microsoft Teams webhook at {url} "
                "returned error {status_code}: {text}".format(
                    url=microsoft_teams_webhook,
                    status_code=response.status_code,
                    text=response.text,
                )
            )
            return
        else:
            return "Microsoft Teams notification succeeded."


def send_webhook_notifications(query, webhook, target_platform):
    session = requests.Session()
    try:
        response = session.post(url=webhook, json=query)
    except requests.ConnectionError:
        logger.warning(
            "Failed to connect to {target_platform} webhook at {url} "
            "after {max_retries} retries.".format(
                url=webhook,
                max_retries=10,
                target_platform=target_platform,
            )
        )
    except Exception as e:
        logger.error(str(e))
    else:
        if response.status_code != 200:
            logger.warning(
                "Request to {target_platform} webhook at {url} "
                "returned error {status_code}: {text}".format(
                    url=webhook,
                    status_code=response.status_code,
                    target_platform=target_platform,
                    text=response.text,
                )
            )
        else:
            return "{target_platform} notification succeeded.".format(
                target_platform=target_platform
            )


def get_runtime_batch_request(
    substituted_runtime_config: CheckpointConfig,
    validation_batch_request: Optional[dict] = None,
) -> BatchRequest:
    if substituted_runtime_config.batch_request is None:
        return (
            validation_batch_request
            if validation_batch_request is None
            else BatchRequest(**validation_batch_request)
        )

    if validation_batch_request is None:
        return BatchRequest(**substituted_runtime_config.batch_request)

    runtime_batch_request_dict: dict = copy.deepcopy(validation_batch_request)
    for key, val in runtime_batch_request_dict.items():
        if (
            val is not None
            and substituted_runtime_config.batch_request.get(key) is not None
        ):
            raise ge_exceptions.CheckpointError(
                f'BatchRequest attribute "{key}" was specified in both validation and top-level CheckpointConfig.'
            )
    runtime_batch_request_dict.update(substituted_runtime_config.batch_request)
    return BatchRequest(**runtime_batch_request_dict)


def get_substituted_validation_dict(
    substituted_runtime_config: CheckpointConfig, validation_dict: dict
) -> dict:
    substituted_validation_dict = {
        "batch_request": get_runtime_batch_request(
            substituted_runtime_config=substituted_runtime_config,
            validation_batch_request=validation_dict.get("batch_request"),
        ),
        "expectation_suite_name": validation_dict.get("expectation_suite_name")
        or substituted_runtime_config.expectation_suite_name,
        "action_list": CheckpointConfig.get_updated_action_list(
            base_action_list=substituted_runtime_config.action_list,
            other_action_list=validation_dict.get("action_list", {}),
        ),
        "evaluation_parameters": nested_update(
            substituted_runtime_config.evaluation_parameters,
            validation_dict.get("evaluation_parameters", {}),
        ),
        "runtime_configuration": nested_update(
            substituted_runtime_config.runtime_configuration,
            validation_dict.get("runtime_configuration", {}),
        ),
    }
    if validation_dict.get("name") is not None:
        substituted_validation_dict["name"] = validation_dict["name"]
    validate_validation_dict(substituted_validation_dict)
    return substituted_validation_dict


def validate_validation_dict(validation_dict: dict):
    if validation_dict.get("batch_request") is None:
        raise ge_exceptions.CheckpointError("validation batch_request cannot be None")
    if not validation_dict.get("expectation_suite_name"):
        raise ge_exceptions.CheckpointError(
            "validation expectation_suite_name must be specified"
        )
    if not validation_dict.get("action_list"):
        raise ge_exceptions.CheckpointError("validation action_list cannot be empty")
