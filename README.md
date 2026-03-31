# Nautobot Golden Config Custom Compliance

custom_compliance implementation for nautobot golden config

This is an implementation of a custom compliance function for Nautobot Golden Config. It can be used as it is written or used as a starting point to create your own custom compliance function.

## What it Does

The point of this custom_compliance is to "trick" hier_config to avoid throwing DuplicateChildErrors.

These errors arise because cisco MDS switches organize their running config having duplicated elements
at the root level (each interfaces fc is present twice). This violates a design principle of hier_config:
the HConfig root object can't have duplicates by design.

The hack is to modify both the actual and the intended configuration *before* giving them to hier_config
for the usual remediation checks.

This function is called inside the compliance_on_save() of the ConfigCompliance object.

## Python Installation

Since the current implementation of Golden Config only allows for a single custom compliance function, each organization will be unique, and as such, this function is not consumable as a simple pip install. You will need to be responsible for adding the `custom_compliance.py` file as part of a python package that gets installed into your Nautobot instance(s) alongside Golden Config. For instance, you can bundle it as part of a [custom plugin](https://docs.nautobot.com/projects/core/en/stable/plugins/development/).


## Configuration

Once you have it installed and in the python path, you will need to add it to the `PLUGINS_CONFIG` section of your `nautobot_config.py` file as such:

```python
PLUGINS_CONFIG = {
    "nautobot_golden_config": {
        "get_custom_compliance": "custom_compliance.compliance.run_custom_compliance"
    }
}

where `custom_compliance` is a folder/package on the same level of the main nautobot folder.
.
└── nautobot
    ├── custom_compliance
    │   ├── __init__.py
    │   └── compliance.py
    ├── nautobot
    │   ├── __init__.py
    │   ├── apps
    │   ├── circuits
    │   ├── cloud
    │   ├── core
    │   ├── data_validation
    ...

```

The custom compliance function will be run on a specific compliance rule only if 

1. `Custom Compliance` field in the rule is set to true
2. the compliance rule name (`Feature` field) must match this value:
`obj.rule.feature.name == "interfaces":` in compliance.py

![sample compliance rule](https://github.com/pastoreerrante/nautobot_golden_config_custom_compliance/blob/main/custom_config_compliance.png?raw=true)

## How does compliance works?

compliance jobs in golden config app is implemented as a nornir task in 
nautobot_golden_config/nornir_plays/config_compliance.py

the python function is called `run_compliance(...)`

this is the heart of the job:

```python
backup_cfg = _open_file_config(backup_file)
intended_cfg = _open_file_config(intended_file)

# here we are looping over plugins/golden-config/compliance-rule/
for rule in rules[obj.platform.network_driver]:
    # for CLI config the subset of the config is really given by netutils
    # from netutils.config.compliance import section_config
    _actual = get_config_element(rule, backup_cfg, obj, logger) # actually calling section_config()
    _intended = get_config_element(rule, intended_cfg, obj, logger)

    # using update_or_create() method to conveniently update actual obj or create new one.
    ConfigCompliance.objects.update_or_create(
        device=obj,
        rule=rule["obj"],
        defaults={
            "actual": _actual,
            "intended": _intended,
            "missing": "",
            "extra": "",
        },
    )

```

```python
rules = get_rules()

def get_rules():
   """A serializer of sorts to return rule mappings as a dictionary."""
   # TODO: Future: Review if creating a proper serializer is the way to go.
   rules = defaultdict(list)
   for compliance_rule in ComplianceRule.objects.all():
       platform = str(compliance_rule.platform.network_driver)
       rules[platform].append(
           {
               "ordered": compliance_rule.config_ordered,
               "obj": compliance_rule,
               "section": compliance_rule.match_config.splitlines(),
           }
       )
   return rules
```

```python
# IMPORTANT: compliance and remediation do happen everytime a ConfigCompliance obj instance
# is created, i.e. for every defined ComplianceRule 
class ConfigCompliance(PrimaryModel):  # pylint: disable=too-many-ancestors
   ...
   ...
   def save(self, *args, **kwargs):
       self.compliance_on_save()
       self.remediation_on_save()
```


```python
 
def compliance_on_save(self):
     """The actual configuration compliance happens here, but the details for actual compliance job would be found in FUNC_MAPPER."""
     if self.rule.custom_compliance:
         if not FUNC_MAPPER.get("custom"):
             raise ValidationError(
                 "Custom type provided, but no `get_custom_compliance` config set, please contact system admin."
             )
         compliance_details = FUNC_MAPPER["custom"](obj=self) # run_custom_compliance runs here
         _verify_get_custom_compliance_data(compliance_details)
     else:
         compliance_details = FUNC_MAPPER[self.rule.config_type](obj=self)

     self.compliance = compliance_details["compliance"]
     self.compliance_int = compliance_details["compliance_int"]
     self.ordered = compliance_details["ordered"]
     self.missing = compliance_details["missing"]
     self.extra = compliance_details["extra"]
```
