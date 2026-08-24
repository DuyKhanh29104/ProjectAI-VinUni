from src.services.ingestion.interactive_menu import (
    KEY_DOWN,
    KEY_UP,
    adapter_menu_options,
    city_menu_options,
    dataset_menu_options,
    move_selection,
    package_count_menu_options,
    render_menu,
    scenario_menu_options,
    source_menu_options,
    time_menu_options,
    topic_menu_options,
)


def test_dataset_menu_options_cover_kitti_and_nuscenes():
    options = dataset_menu_options()

    assert [option.value for option in options] == ["kitti", "nuscenes"]
    assert "Flat" in options[0].description
    assert "Relational" in options[1].description


def test_topic_selector_options_cover_source_modality_city_and_time():
    assert [option.value for option in source_menu_options()] == ["local", "official"]
    assert [option.value for option in adapter_menu_options()] == ["kitti-object-detection", "nuscenes-v1.0-mini"]
    assert [option.value for option in scenario_menu_options()] == ["baseline_easy", "challenging_hard"]
    assert [option.value for option in topic_menu_options()] == ["2d", "3d"]
    assert [option.value for option in package_count_menu_options()] == ["1", "2"]
    assert "boston-seaport" in [option.value for option in city_menu_options("nuscenes")]
    assert "karlsruhe_urban" in [option.value for option in city_menu_options("kitti")]
    assert [option.value for option in time_menu_options()] == ["any", "day", "night"]


def test_arrow_navigation_wraps_around():
    assert move_selection(0, 2, KEY_UP) == 1
    assert move_selection(1, 2, KEY_DOWN) == 0
    assert move_selection(0, 2, "x") == 0


def test_render_menu_marks_selected_option():
    rendered = render_menu(dataset_menu_options(), 1, title="Select dataset family")

    assert "> nuScenes Dataset" in rendered
    assert "  KITTI Dataset" in rendered
    assert "Select dataset family" in rendered
