"""レイアウト検出が返す「種類」の一覧。

上流の `src/config/ndl.yaml` (並び) と `src/ndl_parser.py` (日本語名) を写した。
**2 つの道具で並びも名前も違う。** 古典籍の 4 番は「注」、近代資料の 4 番は「割注」で、
近代資料にだけ「表組」と「タイトル本文」がある。番号は学習時のものなので、
片方の並びをもう片方に使うと、別の種類として読まれる。
"""

from __future__ import annotations

from dataclasses import dataclass

# (ndl.yaml の名前, ndl_parser.py の日本語名)。並びがそのまま種類の番号になる。
_KOTEN: tuple[tuple[str, str], ...] = (
    ("text_block", "本文ブロック"),
    ("line_main", "本文"),
    ("line_caption", "キャプション"),
    ("line_ad", "広告文字"),
    ("line_note", "注"),
    ("line_note_dummy", "注（ダミー）"),
    ("block_fig", "図版"),
    ("block_ad", "広告"),
    ("block_pillar", "柱"),
    ("block_folio", "ノンブル"),
    ("block_rubi", "ルビ"),
    ("block_chart", "組織図"),
    ("block_eqn", "数式"),
    ("block_cfm", "化学式"),
    ("block_eng", "欧文"),
    # 上流の ndl_parser.py に日本語名が無い。古典籍の検出はすべて本文として
    # 返ってくるので、ここが使われることはない。
    ("table", "表組"),
)

_LITE: tuple[tuple[str, str], ...] = (
    ("text_block", "本文ブロック"),
    ("line_main", "本文"),
    ("line_caption", "キャプション"),
    ("line_ad", "広告文字"),
    ("line_note", "割注"),
    ("line_note_tochu", "頭注"),
    ("block_fig", "図版"),
    ("block_ad", "広告"),
    ("block_pillar", "柱"),
    ("block_folio", "ノンブル"),
    ("block_rubi", "ルビ"),
    ("block_chart", "組織図"),
    ("block_eqn", "数式"),
    ("block_cfm", "化学式"),
    ("block_eng", "欧文"),
    ("block_table", "表組"),
    ("line_title", "タイトル本文"),
)


@dataclass(frozen=True)
class Taxonomy:
    names: tuple[str, ...]
    org_names: tuple[str, ...]

    def index(self, name: str) -> int:
        """その種類の番号。持っていなければ -1(「この道具には無い種類」)。"""
        return self.names.index(name) if name in self.names else -1

    def org_name(self, index: int) -> str:
        return self.org_names[index]


def _taxonomy(pairs: tuple[tuple[str, str], ...]) -> Taxonomy:
    return Taxonomy(tuple(p[0] for p in pairs), tuple(p[1] for p in pairs))


KOTEN = _taxonomy(_KOTEN)
LITE = _taxonomy(_LITE)
