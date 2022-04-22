"""
Copyright (c) 2022 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses

All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

import os
import secrets
import string
import sys
from re import template
from time import sleep

import pyzipper
from dnacentersdk import api
from dnacentersdk.exceptions import ApiError
from requests.exceptions import ConnectionError
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.pretty import pprint
from rich.prompt import Confirm

# Init rich Console for text formatting
console = Console()

#################################################
#       -- Required Parameters --
# Please change the following values to fit your environment
#
# DNA Center URL & Authentication credentials:
DNAC_URL = ""
DNAC_USER = ""
DNAC_PASS = ""

# VALID_SNMP_SERVER_HOST is the correct snmp-server host that switches should have configured.
# VALID_SNMP_SERVER_COMMUNITY is the correct community that should be configured.
# Any snmp-server configuration lines that do NOT contain these values will be removed.
VALID_SNMP_SERVER_HOST = ""
VALID_SNMP_SERVER_COMMUNITY = ""

# NEW_CONFIG contains the intended configuration line to be applied to each device
NEW_CONFIG = ""

# PROJECT_NAME is the DNA Center Template Project. Any new templates will be created
# under this project.
# TEMPLATE_NAME will be used when a new Velocity template is created.
PROJECT_NAME = ""
TEMPLATE_NAME = ""

# By default, this script will pull ALL devices in DNAC.
# Modify the below parameters to filter to a subset of devices
DEVICE_FILTER = {
    "hostname": None,
    "management_ip_address": None,
    "family": None,
    "series": None,
    "platform_id": None,
}
LOCATION_FILTER = []
#################################################


# When generating a config export from DNAC, the exports are provided as an encrypted zip file
# We'll generate a unique password here to use for the configuration export
ARCHIVE_SECRET = (
    "".join((secrets.choice(string.ascii_letters + string.digits) for i in range(16)))
    + "!"
)

# Authenticate to DNA Center:
console.print(Panel.fit("Connect to DNA Center", title="Step 1"))
try:
    console.print(f"Connecting to DNA Center at {DNAC_URL}")
    dnac = api.DNACenterAPI(
        base_url=DNAC_URL, username=DNAC_USER, password=DNAC_PASS, verify=False
    )
    console.print("[green][bold]Connected to DNAC")
except ConnectionError:
    console.print(
        "[red][bold]Failed to connect to DNAC. Please check URL & reachability"
    )
    sys.exit(1)
except ApiError:
    console.print("[red][bold]Invalid Login credentials. Please check login info")
    sys.exit(1)


def checkTaskStatus(task):
    """
    General function to check DNA Center task status.

    Parameters:
    task - Unique DNAC task identifier for the target task to monitor

    Returns:
    JSON payload of task response, once task has completed
    """
    while True:
        with console.status(
            "Waiting for task to finish. Current status: Not Started"
        ) as status:
            task_status = dnac.task.get_task_by_id(task.response.taskId)
            status.update(
                f"Waiting for task to finish. Current status: {task_status['response']['progress']}"
            )
            if task_status["response"]["endTime"]:
                console.print("[green][bold]Task finsished!")
                return task_status
            sleep(3)


def downloadFile(task):
    """
    General function to download a file from DNA Center from a task which provides a file download.

    Parameters:
    task - Target task identifier which contains a link to downloadable file

    Returns:
    None - File is saved locally to disk
    """
    # Retrieve config file export from DNAC
    with console.status("Downloading file..."):
        file_location = task["response"]["additionalStatusURL"]
        file_id = file_location.split("/")[4]
        file = dnac.file.download_a_file_by_fileid(file_id=file_id, save_file=True)
        console.print("[green][bold]File Downloaded!")


def unzipConfigFile():
    """
    Unzip configuration export using ARCHIVE_SECRET generated above.

    Parameters:
    None - Local directory is scanned to find downloaded configuration archive

    Returns:
    None - Files are unzipped in local directory to a "configfiles" directory
    """
    with console.status("Unzipping config files..."):
        directory = os.listdir()
        for file in directory:
            if "Export_Configs" in file:
                target_file = file
        with pyzipper.AESZipFile(target_file, "r") as zip:
            try:
                zip.extractall(path="configfiles", pwd=bytes(ARCHIVE_SECRET, "utf-8"))
            except RuntimeError:
                console.print(
                    "[red][bold]Failed to unzip files. Please make sure any old config archives are deleted prior to running this script"
                )
                sys.exit(1)
        console.print("[green][bold]Unzip Complete!")


def validate_snmp_config(device_ip):
    """
    Scans each device configuration file to validate the existence of expected configuration.
    If undesired configuration is found, build a list of each incorrect configuration statement

    Parameters:
    device_ip - DNAC Config exports are placed into folders based on device management IP. Each time
                this function is run, we will process 1 device folder / config.

    Returns:
    bad_config - A list of any unwanted configuration lines, which will be removed from the device
    """
    bad_config = []
    console.print(f"Reading config for device at {device_ip}")
    path = f"./configfiles/{device_ip}/"
    for file in os.listdir(path):
        if file.endswith("RUNNINGCONFIG.cfg"):
            running_config = path + file
    with open(running_config, "r") as config:
        config_found = False
        for line in config:
            if "snmp-server host" in line.strip():
                if (
                    VALID_SNMP_SERVER_HOST in line
                    and VALID_SNMP_SERVER_COMMUNITY in line
                ):
                    console.print(
                        f"[green][bold]Config valid[/bold][/green]: {escape(line.strip())}"
                    )
                    config_found = True
                    pass
                else:
                    console.print(
                        f"[yellow][bold]Config invalid[/bold][/yellow]: {escape(line.strip())}"
                    )
                    config_found = True
                    bad_config.append(line.strip())
        if not config_found:
            console.print(
                f"[yellow][bold]No matching config found for device.[/bold][/yellow]"
            )
    console.print()
    return bad_config


def getProjectID():
    """
    General function to locate DNA Center project identifier, which will be required to
    add/remove templates.

    Parameters:
    PROJECT_NAME - Name of target project to search for

    Returns:
    project_id - Unique identifier for the DNAC project / template group
    """
    # Retrieve UUID for Template project
    console.print("Getting Project List...")
    project = dnac.configuration_templates.get_projects(name=PROJECT_NAME)
    project_id = project[0]["id"]
    return project_id


def generateTemplatePayload(device_list):
    """
    Generates DNA Center template using Velocity scripting.
    For each device we need to modify, we will generate a conditional set of
    "no <config>" statements - which only apply based on target device management IP.
    Lastly, we apply new configuration line to all affected devices

    Parameters:
    device_list - Target dictionary of devices, containing device IP, UUID, and bad config statements

    Returns:
    template_payload - Completed template file to be uploaded to DNAC
    """
    # Create Velocity template payload
    template_payload = []
    with console.status("Generating template payload..."):
        for device in device_list:
            # If there is no bad config to remove, skip this device
            if "bad_config" in device_list[device]:
                # Add conditional to ensure config change only applies to device with matching management IP
                template_payload.append(f"#if($device_ip == '{device}')")
                # Iterate through bad config items, and add to list to negate
                for config_item in device_list[device]["bad_config"]:
                    template_payload.append(f"no {config_item}")
                template_payload.append("#end")
                # Empty new line between each device config block, so template is easier to read
                template_payload.append("")
        # End of template config, apply the new snmp configuration
        template_payload.append(NEW_CONFIG)
        template_payload = "\n".join(template_payload)
        console.print("[green][bold]Template generated!")
        return template_payload


def createNewTemplate(template_payload, device_types):
    """
    Upload & create a new Velocity template.
    Note: If template already exists with the same name, this script will not
          delete or modify the existing template. However, the script will query
          the existing template ID to enable deployment of the template

    Parameters:
    template_payload - Plaintext dump of template contents
    device_types - List of target device types to affect (Routers, Switches, etc)

    Returns:
    template_id - Unique identifier of newly created template
    """
    # Create new template with target configuration
    project_id = getProjectID()
    with console.status("Uploading template to DNA Center...") as status:
        try:
            create_template = dnac.configuration_templates.create_template(
                project_id=project_id,
                name=TEMPLATE_NAME,
                softwareType="IOS-XE",
                deviceTypes=device_types,
                payload={"templateContent": template_payload},
                version="2",
                language="VELOCITY",
            )
            console.print("[green][bold]Template uploaded!")
            error = False
        except ApiError:
            console.print("[red]Error creating template. Template may already exist.")
            error = True
    # If we hit an error creating template, then it likely already exists
    # and we'll prompt whether or not to continue running this script
    if error:
        if not Confirm.ask("Continue", default=True):
            sys.exit(1)

    with console.status("Querying DNAC for Template UUID..."):
        project = dnac.configuration_templates.get_projects(name=PROJECT_NAME)
        for template in project[0]["templates"]:
            if template["name"] == TEMPLATE_NAME:
                template_id = template["id"]

    with console.status("Committing template version..."):
        version = dnac.configuration_templates.version_template(
            comments="Commit via API", templateId=template_id
        )
        console.print("[green][bold]Template committed!")
    return template_id


def deployTemplate(template_id, device_list):
    """
    Push new configuration template to all target devices.


    Parameters:
    template_id - Template UUID for desired template to deploy via DNAC
    device_list - List of target devices where template will be applied

    Returns:
    None - Deployment status will be printed to screen
    """
    console.print(f"Deploying template to {len(device_list)} devices.")
    with console.status("Starting deployment...") as status:
        sleep(2)
        deploy_template = dnac.configuration_templates.deploy_template(
            templateId=template_id,
            targetInfo=device_list,
        )
        # Grab deployment UUID
        deploy_id = str(deploy_template.deploymentId).split(":")[-1].strip()
        while True:
            # Monitor deployment status to see when it completes
            response = dnac.configuration_templates.get_template_deployment_status(
                deployment_id=deploy_id
            )
            status.update(f"Current status: {response['status']}")
            if response["status"] == "SUCCESS":
                console.print("[green][bold]Deployment complete!")
                break
            if response["status"] == "FAILURE":
                console.print("[red][bold]Deployment Failed! See below for errors:")
                pprint(response)
            sleep(3)


def run():
    """
    Primary function for script execution & workflow
    """
    # Query device list
    console.print()
    console.print(Panel.fit("Retrieve device list from DNA Center", title="Step 2"))
    console.print("Getting device list...")
    devices = dnac.devices.get_device_list(**DEVICE_FILTER)

    # Build dictionary mapping Device IP address to UUID
    target_devices = {}
    for device in devices.response:
        # If filtering by location, we need to get location info from device_detail API
        if len(LOCATION_FILTER) >= 1:
            device_detail = dnac.devices.get_device_detail(
                identifier="uuid", search_by=device["id"]
            )
            if device_detail.response["location"] not in LOCATION_FILTER:
                # Skip if device is not in desired location
                continue
        # Add device to list
        target_devices[device["managementIpAddress"]] = {"id": device["id"]}

    # Device product family / series will be required when creating a new template
    # So for each device we are targeting, we'll build that list of types here
    device_types = []
    for device in devices.response:
        device_types.append(
            {"productFamily": device["family"], "productSeries": device["series"]}
        )

    console.print(f"[bold]Found {len(target_devices)} devices that matched criteria")

    console.print()
    console.print(Panel.fit("Export current device configurations", title="Step 3"))
    console.print(f"Requesting config export...")
    task = dnac.configuration_archive.export_device_configurations(
        deviceId=[target_devices[device]["id"] for device in target_devices],
        password=ARCHIVE_SECRET,
    )

    # Check task status & download config file
    task_response = checkTaskStatus(task)

    # Download file
    downloadFile(task_response)

    # Unzip config files
    unzipConfigFile()

    # Run comparison against expected configuration
    console.print()
    console.print(
        Panel.fit(
            "Compare current configurations to expected configurations", title="Step 4"
        )
    )

    # Build a list of which devices to deploy changes
    deployable_devices = []
    for device in target_devices:
        # Run validation against current config vs expected config
        result = validate_snmp_config(device)
        # If any bad configuration is found, append it to target_devices dictionary
        if result:
            target_devices[device]["bad_config"] = result
        # Also add device to list of devices to push template to
        deployable_devices.append(
            {
                "id": device,
                "type": "MANAGED_DEVICE_IP",
                "params": {"device_ip": device},
            }
        )

    # Generate template file based on config that needs to be modified
    console.print()
    console.print(
        Panel.fit(
            "Create new DNA Center template to modify device configurations",
            title="Step 5",
        )
    )
    template_payload = generateTemplatePayload(target_devices)
    # Upload template to DNAC
    template_id = createNewTemplate(template_payload, device_types)

    # Deploy changes to all devices with bad configurations
    console.print()
    console.print(
        Panel.fit(
            "Deploy template to devices with incorrect configurations",
            title="Step 6",
        )
    )
    # Display warning message
    console.print(
        "[yellow]Warning: Config deployment may take several minutes and may fail for a variety of reasons."
    )
    console.print(
        "[yellow]You may want to validate the template contents prior to deploying the template to all devices."
    )
    console.print()
    console.print(
        "If you choose not to deploy the template now, it can be deployed manually from the DNA Center web interface"
    )
    console.print("or by running this script again.")
    console.print()
    # Prompt to confirm - otherwise template can still be pushed to devices via DNAC Web UI
    if not Confirm.ask(
        f"Are you sure you want to deploy these changes to {len(deployable_devices)} devices",
        default=False,
    ):
        console.print(
            "Skipping automatic deployment. Please push template manually from DNA Center web interface!"
        )
        sys.exit(1)
    else:
        deployTemplate(template_id, deployable_devices)


if __name__ == "__main__":
    run()
