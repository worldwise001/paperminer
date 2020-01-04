import re
from typing import List, Optional, Dict, Tuple, Any, cast

from pdfminer.layout import LTTextBox, LTAnno
from pdfminer.pdffont import PDFFont
from pdfminer.pdfinterp import PDFResourceManager


class PaperResourceManager(PDFResourceManager):
    def __init__(self) -> None:
        super().__init__()
        self.section_header_ref: List[LTTextBox] = []
        self.text_ref: List[LTTextBox] = []
        self.figure_ref: List[LTTextBox] = []
        self.abstract_ref: Optional[LTTextBox] = None
        self.table_ref: List[LTTextBox] = []
        self.ref_ref: Optional[LTTextBox] = None
        self.top_margin_ref: Optional[LTTextBox] = None
        self.left_margin: float = 612
        self.right_margin: float = 0
        self.after_title = False
        self.after_abstract = False
        self.after_ref = False
        self.section_header_font: Optional[PDFFont] = None
        self.section_header_font_size: float = 0
        self.font_map: Dict[Tuple[PDFFont, float], int] = {}
        self.body_font: Optional[PDFFont] = None
        self.body_font_size: float = 0
        self.tiny_font: Optional[PDFFont] = None
        self.tiny_font_size: float = 0

    def post_process(self) -> None:
        # figure out section header fonts
        font_list = [(item.font, item.fontsize) for item in self.section_header_ref]
        self.section_header_font, self.section_header_font_size = get_most_popular(font_list)

        max_key = None
        for k in self.font_map.keys():
            if not max_key or self.font_map[k] > self.font_map[max_key]:
                max_key = k
        self.body_font, self.body_font_size = cast(Tuple[PDFFont, float], max_key)

        next_max_key = None
        for k in self.font_map.keys():
            if k != max_key and (not next_max_key or self.font_map[k] > self.font_map[next_max_key]):
                next_max_key = k
        self.tiny_font, self.tiny_font_size = cast(Tuple[PDFFont, float], next_max_key)

    def tally(self, font: PDFFont, fontsize: float) -> None:
        item = (font, fontsize)
        if item not in self.font_map:
            self.font_map[item] = 0
        self.font_map[item] += 1


def get_most_popular(item_list: List[Any]) -> Any:
    freq: Dict[Any, int] = {}
    item: Any = None
    max_key: Any = None
    for item in item_list:
        if item not in freq:
            freq[item] = 0
        freq[item] += 1
    if item:
        max_key = item
        for k in freq.keys():
            if freq[k] > freq[max_key]:
                max_key = k
    return max_key


intro_header_pattern = re.compile('[\\d.]* ?introduction( .+)?', re.IGNORECASE)
ref_header_pattern = re.compile('[\\d.]* ?reference( .+)?', re.IGNORECASE)
ref_pattern = re.compile('\\[\\d\\]\\s.*')
abstract_header_pattern = re.compile('[\\d.]* ?abstract( .+)?', re.IGNORECASE)
background_header_pattern = re.compile('[\\d.]* ?background( .+)?', re.IGNORECASE)
figure_pattern = re.compile('figure( \\w\\d*)?: ?.*', re.IGNORECASE)
table_pattern = re.compile('table( \\w\\d*)?: ?.*', re.IGNORECASE)


def compare_if_citation(d: float, obj1: LTTextBox, obj2: LTTextBox, x0_eval: bool) -> bool:
    if ref_pattern.match(obj1.get_text()):
        obj1_x0 = obj1.x0
        past_space = False
        for item in obj1:
            if isinstance(item, LTAnno):
                past_space = True
                continue
            obj1_x0 = item.x0
            if past_space:
                break
        x0_eval = x0_eval or (abs(obj1_x0 - obj2.x0) < d and
                              (abs(obj1.y0 - obj2.y1) < d*2 or abs(obj2.y0 - obj1.y1) < d*2))
    return x0_eval
