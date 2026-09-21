"""IIIF マニフェストの読み取り。取り寄せには行かず、形の見分け方だけを見る。"""

from __future__ import annotations

import pytest

from local_ocr.core import iiif

V3 = {
    "@context": "http://iiif.io/api/presentation/3/context.json",
    "type": "Manifest",
    "label": {"ja": ["酉蓮社本"], "en": ["Yurensha"]},
    "items": [
        {
            "type": "Canvas",
            "label": {"none": ["1 オ"]},
            "width": 4000,
            "height": 3000,
            "items": [
                {
                    "type": "AnnotationPage",
                    "items": [
                        {
                            "type": "Annotation",
                            "motivation": "painting",
                            "body": {
                                "id": "https://example.org/iiif/p1/full/full/0/default.jpg",
                                "type": "Image",
                                "width": 4000,
                                "height": 3000,
                                "service": [
                                    {
                                        "id": "https://example.org/iiif/p1",
                                        "type": "ImageService3",
                                    }
                                ],
                            },
                        }
                    ],
                }
            ],
        }
    ],
}

V2 = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "@type": "sc:Manifest",
    "label": "東洋文庫本",
    "sequences": [
        {
            "canvases": [
                {
                    "@id": "https://example.org/canvas/1",
                    "label": "1",
                    "width": 800,
                    "height": 1200,
                    "images": [
                        {
                            "resource": {
                                "@id": "https://example.org/iiif/p1/full/full/0/default.jpg",
                                "width": 800,
                                "height": 1200,
                                "service": {
                                    "@id": "https://example.org/iiif/p1",
                                    "profile": "http://iiif.io/api/image/2/level2.json",
                                },
                            }
                        }
                    ],
                }
            ]
        }
    ],
}


def test_reads_a_v3_manifest():
    manifest = iiif.parse(V3, lang="ja")
    assert manifest.label == "酉蓮社本"
    assert len(manifest.canvases) == 1
    canvas = manifest.canvases[0]
    assert canvas.label == "1 オ"
    # 4000x3000 は大きすぎる。長辺 1600 に収まる幅を頼む。
    assert canvas.image_url == "https://example.org/iiif/p1/full/1600,/0/default.jpg"


def test_reads_a_v2_manifest():
    manifest = iiif.parse(V2)
    assert manifest.label == "東洋文庫本"
    canvas = manifest.canvases[0]
    assert canvas.label == "1"
    # 縦長。長辺 1200 は上限に収まるので、そのままの幅を頼む。
    assert canvas.image_url == "https://example.org/iiif/p1/full/800,/0/default.jpg"


def test_the_manifest_label_follows_the_screen_language():
    assert iiif.parse(V3, lang="en").label == "Yurensha"


def test_a_page_without_an_image_service_is_taken_as_it_is():
    """サービスが無いマニフェストでも読める。大きさは指定できないので原寸。"""
    doc = {
        "type": "Manifest",
        "items": [
            {
                "type": "Canvas",
                "items": [
                    {
                        "items": [
                            {
                                "motivation": "painting",
                                "body": {"id": "https://example.org/plain.jpg", "type": "Image"},
                            }
                        ]
                    }
                ],
            }
        ],
    }
    assert iiif.parse(doc).canvases[0].image_url == "https://example.org/plain.jpg"


def test_a_choice_of_images_takes_the_first():
    """原本と赤外線が並ぶことがある。選ばせるのは、この道具の仕事ではない。"""
    body = {
        "type": "Choice",
        "items": [
            {"id": "https://example.org/a.jpg", "type": "Image"},
            {"id": "https://example.org/b.jpg", "type": "Image"},
        ],
    }
    doc = {
        "type": "Manifest",
        "items": [
            {"type": "Canvas", "items": [{"items": [{"motivation": "painting", "body": body}]}]}
        ],
    }
    assert iiif.parse(doc).canvases[0].image_url == "https://example.org/a.jpg"


def test_a_canvas_without_a_label_is_numbered():
    doc = {
        "type": "Manifest",
        "items": [
            {
                "type": "Canvas",
                "items": [
                    {
                        "items": [
                            {"motivation": "painting", "body": {"id": "https://example.org/x.jpg"}}
                        ]
                    }
                ],
            }
        ],
    }
    assert iiif.parse(doc).canvases[0].label == "1"


def test_a_collection_says_so_instead_of_coming_up_empty():
    with pytest.raises(iiif.ManifestError) as caught:
        iiif.parse({"type": "Collection", "items": []})
    assert caught.value.key == "iiif.error.collection"


def test_a_manifest_without_images_is_an_error():
    with pytest.raises(iiif.ManifestError) as caught:
        iiif.parse({"type": "Manifest", "items": []})
    assert caught.value.key == "iiif.error.empty"


def test_something_that_is_not_json_at_all():
    with pytest.raises(iiif.ManifestError) as caught:
        iiif.parse("<html>")
    assert caught.value.key == "iiif.error.parse"


@pytest.mark.parametrize(
    ("width", "height", "want"),
    [
        (4000, 3000, "1600,"),  # 横長。長辺を 1600 に
        (3000, 4000, "1200,"),  # 縦長。高さが 1600 になる幅を頼む
        (800, 600, "800,"),  # 小さいものは縮めない
        (0, 0, "1600,"),  # 寸法が書いていない。幅だけ決め打ち
    ],
)
def test_asks_for_a_size_that_fits(width: int, height: int, want: str):
    body = {"service": [{"id": "https://example.org/iiif/p"}]}
    assert iiif.image_url(body, width, height).endswith(f"/full/{want}/0/default.jpg")


def test_the_cache_gives_one_file_per_url():
    a = iiif.cache_path("https://example.org/a.jpg")
    b = iiif.cache_path("https://example.org/b.jpg")
    assert a != b
    assert a == iiif.cache_path("https://example.org/a.jpg")
    assert a.parent == iiif.cache_dir()
