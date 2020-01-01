from pdfminer.layout import LTContainer, LTTextLineHorizontal, LTTextLineVertical, LTTextContainer, LTAnno, \
    LTChar, LTLayoutContainer
from pdfminer.utils import bbox2str


class LTLayoutContainerExtended(LTLayoutContainer):

    def __init__(self, bbox):
        super().__init__(bbox)
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


class LTCharExtended(LTChar):
    """Actual letter in the text as a Unicode string."""

    def __init__(self, matrix, font, fontsize, scaling, rise, text, textwidth, textdisp, ncs, graphicstate):
        super().__init__(matrix, font, fontsize, scaling, rise, text, textwidth, textdisp, ncs, graphicstate)
        self.font = font
        self.fontsize = fontsize
        self.textwidth = textwidth


class LTPageExtended(LTLayoutContainerExtended):

    def __init__(self, pageid, bbox, rotate=0):
        LTLayoutContainerExtended.__init__(self, bbox)
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


class LTPageHeader(LTTextContainer):
    def __init__(self, word_margin):
        LTTextContainer.__init__(self)
        self.word_margin = word_margin
        return

    def __repr__(self):
        return ('<%s %s %r>' %
                (self.__class__.__name__, bbox2str(self.bbox),
                 self.get_text()))

    def analyze(self, laparams):
        LTTextContainer.analyze(self, laparams)
        LTContainer.add(self, LTAnno('\n'))
        return

    def find_neighbors(self, plane, ratio):
        raise NotImplementedError


class LTPageFooter(LTTextContainer):
    pass


class LTSectionHeader(LTTextContainer):
    pass


class LTSectionBody(LTTextContainer):
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
