from collections import Counter

from nautobot_golden_config.models import FUNC_MAPPER

REDUNDANT_LINE = "interface fc"


def _is_interface(x):
    x.startswith(REDUNDANT_LINE)


def custom_remediation(custom_obj):
    print("called custom remediation")
    print(f"{custom_obj=}")


def _is_deduplicatable(config):
    """
    Args:
      config: List[str] - list of strings who supposedly contains duplicates

    Returns:
      Bool - True if config looks to be deduplicatable, i.e. if each item in the list appears twice
             else False
    """
    #
    # config has this shape:
    # ["interface fc1/1", "interface fc1/2", ..., "interface fc1/1", "interface fc1/2", ...]
    #
    # >>> Counter(config)
    # >>> Counter({'interface fc1/1': 2, 'interface fc1/2': 2, 'interface fc1/3': 2 ...)
    return all(map(lambda x: x == 2, Counter(config).values()))


def _deduplicate_config(config, redundant_line, predicate):
    """
    Args:
      config: str - this is a cisco MDS running config
      redundant_line: str - this is the string to find in the first half of the config
                      and to be removed because it's duplicated in the second half
      predicate: Callable[str] -> Bool - needed to perform consistency check on config

    Returns:
      deduplicated_config: str - this the deduplicated configuration, i.e. the original config without redundant lines

    Raises:
      AssertionError: if consistency check fails, i.e. if the given config is not deduplicatable because
                      there are no duplicates

    """
    # we assume `config` is a cisco MDS config having this shape:
    # ```
    # interface fc1/1         ! redundant part to be removed
    # interface fc1/2         ! redundant part to be removed
    # ...
    # interface fc1/1         ! real stuff
    #   port-license acquire  ! real stuff
    # interface fc1/2         ! real stuff
    #   port-license acquire  ! real stuff
    # ```
    config_lst = config.splitlines()

    # remove every line in config_lst we don't care about.
    # This makes _is_deduplicatable job really easy to be performed.
    # predicate is a function called on every line of config_lst.
    # If it returns True, the line stays, else it gets removed
    filtered_config = list(filter(predicate, config_lst))

    if not _is_deduplicatable(filtered_config):
        error_msg = f"consistency error: each '{redundant_line}' in the configuration must appear exactly twice"
        raise AssertionError(error_msg)

    # deduplication happens here
    removed_config_lines = []
    for config_line in config_lst:
        if config_line.startswith(redundant_line) and config_line not in removed_config_lines:
            removed_config_lines.append(config_line)
            config_lst.remove(config_line)

    # we turn back the configuration from list into a pure string, logically reversing .splitlines()
    deduplicated_config = "\n".join(config_lst)

    return deduplicated_config


def custom_compliance(obj):
    """
    Args:
      obj: The ConfigCompliance instance containing device, rule, actual, and intended configuration data.

    Returns:
      compliance_details: dict[str, Any] this dict captures the result of the compliance check


    The point of this custom_compliance is to "trick" hier_config to avoid throwing DuplicateChildErrors.

    These errors arise because cisco MDS switches organize their running config having duplicated elements
    at the root level (each interfaces fc is present twice). This violates a design principle of hier_config:
    the HConfig root object can't have duplicates by design.

    The hack is to modify both the actual and the intended configuration *before* giving them to hier_config
    for the usual remediation checks.

    This function is called inside the compliance_on_save() of the ConfigCompliance object.
    """
    print("called custom_compliance")
    print(f"{obj.actual=}")
    print(f"{obj.intended=}")

    # in theory custom_compliance() fun might be called over multiple Compliance Rules
    # but custom compliance logic might be different for each compliance rule.
    # this custom logic must be applied only for the compliance rule called "interfaces"
    if obj.rule.feature.name == "interfaces":
        actual_config_deduplicated = _deduplicate_config(obj.actual, REDUNDANT_LINE, _is_interface)
        intended_config_deduplicated = _deduplicate_config(obj.intended, REDUNDANT_LINE, _is_interface)
        # here we are overriding the original actual and intended configurations with our own
        # version to make hier_config happy
        obj.actual = actual_config_deduplicated
        obj.intended = intended_config_deduplicated

        print(f"{actual_config_deduplicated=}")
        print(f"{intended_config_deduplicated=}")

    # here we are calling the original compliance function according to the type
    # of the compliance rule: CLI/JSON/XML, e.g. _get_cli_compliance() for CLI compliance rules
    compliance_details = FUNC_MAPPER[obj.rule.config_type](obj)
    return compliance_details
