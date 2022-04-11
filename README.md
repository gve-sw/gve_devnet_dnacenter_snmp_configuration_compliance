# Cisco DNA Center - SNMP Configuration Compliance

This is a sample project to demonstrate performing the following tasks:
 - Query DNA center for device configuration
 - Search device configuration for unknown config & known good config
 - Auto-generate device configuration to remove bad configuration & apply known good configuration
 - Upload template to DNA Center
 - Auto-provision template to appropriate devices

## **Contacts**
* Matt Schmitz (mattsc@cisco.com)

## **Solution Components**
* Cisco DNA Center

## **Installation/Configuration**

**[Step 1] Clone repo:**
```bash
git clone <repo_url>
```

**[Step 2] Install required dependencies:**
```bash
pip install -r requirements.txt
```

**[Step 3] Configure required variables:**

Configure the following values within `dnac.py`:

```python
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
# For example, "snmp-server host <address> version 2c <community string>"
NEW_CONFIG = ""

# PROJECT_NAME is the DNA Center Template Project. Any new templates will be created
# under this project.
# TEMPLATE_NAME will be used when a new Velocity template is created.
PROJECT_NAME = ""
TEMPLATE_NAME = ""

# By default, this script will pull ALL devices in DNAC. 
# Modify the below parameters to filter to a subset of devices
DEVICE_FILTER = {"hostname": None,
                 "management_ip_address": None,
                 "family": ['Switches and Hubs', 'Routers'],
                 "series": None,
                 "platform_id": None
                 }
LOCATION_FILTER = []
#################################################
```


## **Usage**

After all required configuration items are in place, run the application with the following command:

```
python dnac.py
```

The script will run automatically & print out progress on the terminal. See screenshot below for an example. 

**Note:** By design, this script does not clean up any local files or DNA Center templates between executions. 
 - Before each execution, ensure that the local directory does not contain any configuration archives & delete the `./configfiles` directory which stores the unzipped configurations.
 - If a DNA Center template with the same name already exists, this script **will not** overwrite. Please delete the template, or edit the `TEMPLATE_NAME` variable to specify a new template name.


### **Notes on usage**

 - This script leverages DNA Center config archives to retrieve SNMP configuration information. DNA Center CommandRunner could not be used, due to SNMP communities being classified as sensitive information - and therefore masked from the CommandRunner output.
 - The configuration archives are encrypted by DNA Center before they are available to download by this script. This script creates a one-time randomly generated secret to use as the encryption key. 
 - **This temporary encryption key is not stored or printed.** Any downloaded configuration archives may then be unable to be decrypted after running this script. If you wish to manually specify an encryption password, please edit the `ARCHIVE_SECRET` variable.
 - Upon successful execution, a DNA Center template will be generated. The script will prompt before provisioning this template to the target devices. You have the option to not deploy automatically, and instead provision manually through DNA Center. 
 - **When initially testing this script, please double-check the auto-generated template to ensure the generated configuration matches the expected device changes.**

# Screenshots

**Sample of script execution:**

![/IMAGES/dnac-py.png](/IMAGES/dnac-py.png)



### LICENSE

Provided under Cisco Sample Code License, for details see [LICENSE](LICENSE.md)

### CODE_OF_CONDUCT

Our code of conduct is available [here](CODE_OF_CONDUCT.md)

### CONTRIBUTING

See our contributing guidelines [here](CONTRIBUTING.md)

#### DISCLAIMER:
<b>Please note:</b> This script is meant for demo purposes only. All tools/ scripts in this repo are released for use "AS IS" without any warranties of any kind, including, but not limited to their installation, use, or performance. Any use of these scripts and tools is at your own risk. There is no guarantee that they have been through thorough testing in a comparable environment and we are not responsible for any damage or data loss incurred with their use.
You are responsible for reviewing and testing any scripts you run thoroughly before use in any non-testing environment.