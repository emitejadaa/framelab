import pytest

from framelab.options import Option, OptionError, OptionsNamespace, build_default_registry


@pytest.fixture
def reg():
    return build_default_registry()


def test_defaults(reg):
    assert reg.get("general.theme") == "system"
    assert reg.get("general.accent") == "#3B82F6"
    assert reg.get("code.style") == "steps"


def test_set_and_reset(reg):
    reg.set("general.theme", "dark")
    assert reg.get("general.theme") == "dark"
    reg.reset("general.theme")
    assert reg.get("general.theme") == "system"


def test_rejects_value_outside_choices(reg):
    with pytest.raises(OptionError, match="general.theme"):
        reg.set("general.theme", "purple")


def test_rejects_wrong_type_and_bool_as_int(reg):
    with pytest.raises(OptionError):
        reg.set("general.inline_height", "720")
    with pytest.raises(OptionError):
        reg.set("general.inline_height", True)
    reg.set("general.inline_height", 800)
    assert reg.get("general.inline_height") == 800


def test_unknown_key(reg):
    with pytest.raises(KeyError):
        reg.get("nope.nothing")


def test_duplicate_registration(reg):
    with pytest.raises(ValueError):
        reg.register(Option("general.theme", "system", str, ("system",)))


def test_invalid_default_is_rejected():
    reg = build_default_registry()
    with pytest.raises(OptionError):
        reg.register(Option("x.y", 3, str))


def test_namespace_attribute_access(reg):
    ns = OptionsNamespace(reg)
    assert ns.general.theme == "system"
    ns.general.theme = "light"
    assert reg.get("general.theme") == "light"
    assert "theme" in dir(ns.general)
    with pytest.raises(AttributeError):
        ns.general.nothing  # noqa: B018
    with pytest.raises(AttributeError):
        ns.general.nothing = 1


def test_namespace_repr_lists_values(reg):
    assert "code.style = 'steps'" in repr(OptionsNamespace(reg).code)


def test_describe_shape(reg):
    items = {d["key"]: d for d in reg.describe()}
    assert items["general.theme"] == {
        "key": "general.theme",
        "category": "general",
        "value": "system",
        "default": "system",
        "type": "str",
        "i18n_key": "prefs.general.theme",
        "choices": ["system", "light", "dark"],
    }
    assert "choices" not in items["general.accent"]


def test_subscribe_notifies_and_unsubscribes(reg):
    seen = []
    off = reg.subscribe(lambda k, v: seen.append((k, v)))
    reg.set("general.theme", "dark")
    reg.reset("general.theme")
    off()
    reg.set("general.theme", "light")
    assert seen == [("general.theme", "dark"), ("general.theme", "system")]


def test_module_level_helpers():
    import framelab

    framelab.set_option("general.theme", "dark")
    try:
        assert framelab.get_option("general.theme") == "dark"
        assert framelab.options.general.theme == "dark"
    finally:
        framelab.reset_option("general.theme")
