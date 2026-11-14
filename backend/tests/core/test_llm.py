from app.core.llm import deepinfra_model


def test_building_without_a_key_does_not_raise():
    assert deepinfra_model("", "x").model_name == "x"
