from pdfminer.layout import LTTextLineHorizontal, LTTextLineVertical, LTTextContainer, LTChar, LTLayoutContainer, LTTextBoxVertical, LTTextBoxHorizontal
from pdfminer.utils import bbox2str, Plane, uniq


class LTLayoutContainerExtended(LTLayoutContainer):
    def __init__(self, bbox, rsrcmgr = None):
        super().__init__(bbox)
        self.rsrcmgr = rsrcmgr
        return

    # group_objects: group text object to textlines.
    def group_objects(self, laparams, objs):
        obj0 = None
        line = None
        for obj1 in objs:
            if obj0 is not None:
                # halign: obj0 and obj1 is horizontally aligned.
                #
                #   +------+ - - -
                #   | obj0 | - - +------+   -
                #   |      |     | obj1 |   | (line_overlap)
                #   +------+ - - |      |   -
                #          - - - +------+
                #
                #          |<--->|
                #        (char_margin)
                halign = (obj0.is_compatible(obj1) and
                          obj0.is_voverlap(obj1) and
                          (min(obj0.height, obj1.height) * laparams.line_overlap <
                           obj0.voverlap(obj1)) and
                          (obj0.hdistance(obj1) <
                           max(obj0.width, obj1.width) * laparams.char_margin))

                # valign: obj0 and obj1 is vertically aligned.
                #
                #   +------+
                #   | obj0 |
                #   |      |
                #   +------+ - - -
                #     |    |     | (char_margin)
                #     +------+ - -
                #     | obj1 |
                #     |      |
                #     +------+
                #
                #     |<-->|
                #   (line_overlap)
                valign = (laparams.detect_vertical and
                          obj0.is_compatible(obj1) and
                          obj0.is_hoverlap(obj1) and
                          (min(obj0.width, obj1.width) * laparams.line_overlap <
                           obj0.hoverlap(obj1)) and
                          (obj0.vdistance(obj1) <
                           max(obj0.height, obj1.height) * laparams.char_margin))

                if ((halign and isinstance(line, LTTextLineHorizontalExtended)) or
                        (valign and isinstance(line, LTTextLineVertical))):
                    line.add(obj1)
                elif line is not None:
                    yield line
                    line = None
                else:
                    if valign and not halign:
                        line = LTTextLineVertical(laparams.word_margin)
                        line.add(obj0)
                        line.add(obj1)
                    elif halign and not valign:
                        line = LTTextLineHorizontalExtended(laparams.word_margin)
                        line.add(obj0)
                        line.add(obj1)
                    else:
                        line = LTTextLineHorizontalExtended(laparams.word_margin)
                        line.add(obj0)
                        yield line
                        line = None
            obj0 = obj1
        if line is None:
            line = LTTextLineHorizontalExtended(laparams.word_margin)
            line.add(obj0)
        yield line
        return

    # group_textlines: group neighboring lines to textboxes.
    def group_textlines(self, laparams, lines):
        plane = Plane(self.bbox)
        plane.extend(lines)
        boxes = {}
        for line in lines:
            if isinstance(line, LTTextLineHorizontalExtended):
                box = LTTextBoxHorizontal()
                if self.rsrcmgr:
                    klass = line.maybe_classify(self.rsrcmgr)
                    if klass == LTTitle:
                        self.rsrcmgr.after_title = True
                    elif not self.rsrcmgr.after_abstract and klass == LTSectionHeader:
                        self.rsrcmgr.after_abstract = True
                    box = klass()
            else:
                box = LTTextBoxVertical()
            if not isinstance(box, LTTitle) and not isinstance(box, LTSectionHeader):
                neighbors = line.find_neighbors_with_rsrcmgr(plane, laparams.line_margin, self.rsrcmgr)
                if line not in neighbors:
                    continue
            else:
                neighbors = [line]
            members = []
            for obj1 in neighbors:
                members.append(obj1)
                if obj1 in boxes:
                    members.extend(boxes.pop(obj1))
            for obj in uniq(members):
                box.add(obj)
                boxes[obj] = box
        done = set()
        for line in lines:
            if line not in boxes:
                continue
            box = boxes[line]
            if box in done:
                continue
            done.add(box)
            if not box.is_empty():
                yield box
        return


class LTCharExtended(LTChar):
    """Actual letter in the text as a Unicode string."""

    def __init__(self, matrix, font, fontsize, scaling, rise, text, textwidth, textdisp, ncs, graphicstate):
        super().__init__(matrix, font, fontsize, scaling, rise, text, textwidth, textdisp, ncs, graphicstate)
        self.font = font
        self.fontsize = fontsize
        self.textwidth = textwidth


class LTPageExtended(LTLayoutContainerExtended):

    def __init__(self, pageid, bbox, rotate=0, rsrcmgr=None):
        LTLayoutContainerExtended.__init__(self, bbox, rsrcmgr)
        self.pageid = pageid
        self.rotate = rotate
        return

    def __repr__(self):
        return ('<%s(%r) %s rotate=%r>' %
                (self.__class__.__name__, self.pageid,
                 bbox2str(self.bbox), self.rotate))


class LTTextLineHorizontalExtended(LTTextLineHorizontal):
    def __init__(self, word_margin):
        super().__init__(word_margin)
        self.fontsize = 0
        self.font = None

    def add(self, obj):
        super().add(obj)
        if len(self._objs) == 1:
            self.font = self._objs[0].font
            self.fontsize = self._objs[0].fontsize

    @property
    def left_margin(self):
        left_margin = 612
        for item in self:
            if isinstance(item, LTCharExtended) and item.x0 < left_margin:
                left_margin = item.x0
        return left_margin

    @property
    def right_margin(self):
        right_margin = 0
        for item in self:
            if isinstance(item, LTCharExtended) and item.x1 > right_margin:
                right_margin = item.x0
        return right_margin

    def maybe_compare(self, other_line):
        if not isinstance(other_line, LTTextLineHorizontalExtended):
            return False
        if self.get_text().strip() != other_line.get_text().strip():
            return False
        if self.bbox != other_line.bbox:
            return False
        return True

    def maybe_classify(self, rsrcmgr):
        if not rsrcmgr:
            return LTTextBoxHorizontal
        if self._objs[0].y0 > rsrcmgr.top_margin_ref.y1:
            return LTPageMargin
        if self.maybe_compare(rsrcmgr.top_margin_ref):
            return LTTitle
        if rsrcmgr.after_title:
            if rsrcmgr.section_header_font == self.font and rsrcmgr.section_header_font_size == self.fontsize:
                return LTSectionHeader
            if not rsrcmgr.after_abstract:
                return LTAuthor
        return LTTextBoxHorizontal

    def find_neighbors_with_rsrcmgr(self, plane, ratio, rsrcmgr):
        d = ratio*self.height
        objs = plane.find((self.x0, self.y0-d, self.x1, self.y1+d))
        classification = self.maybe_classify(rsrcmgr)
        return [obj for obj in objs
                if (isinstance(obj, LTTextLineHorizontalExtended) and
                    classification == obj.maybe_classify(rsrcmgr) and
                    (
                        (abs(obj.height-self.height) < d and (abs(obj.x0-self.x0) < d or abs(obj.x1-self.x1) < d)) or
                        classification == LTAuthor or
                        classification == LTPageMargin
                    )
                    )]


class LTPageMargin(LTTextBoxHorizontal):
    pass

class LTTitle(LTTextBoxHorizontal):
    pass


class LTAuthor(LTTextBoxHorizontal):
    pass


class LTSectionHeader(LTTextBoxHorizontal):
    pass


class LTSectionBody(LTTextBoxHorizontal):
    pass


class LTCitation(LTTextContainer):
    def __init__(self):
        LTTextContainer.__init__(self)
        self.ref = 0
        self.author = []
        self.title = None
        self.venue = None
        self.date = '0000'
        self.link = ''
        return

    pass


class LTEquation(LTTextContainer):
    pass


class LTCaption(LTTextContainer):
    pass
