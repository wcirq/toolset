from enum import IntFlag

import comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0 as __wrapper_module__
from comtypes.gen._00020430_0000_0000_C000_000000000046_0_2_0 import (
    OLE_XSIZE_HIMETRIC, OLE_XPOS_CONTAINER, IUnknown,
    FONTSTRIKETHROUGH, OLE_YSIZE_HIMETRIC, OLE_COLOR, IPictureDisp,
    DISPPROPERTY, StdPicture, OLE_HANDLE, CoClass, FONTBOLD,
    IFontEventsDisp, StdFont, OLE_OPTEXCLUSIVE, FONTNAME, EXCEPINFO,
    Unchecked, GUID, _lcid, BSTR, FONTUNDERSCORE, OLE_CANCELBOOL,
    OLE_YSIZE_PIXELS, IPicture, IFontDisp, Gray, OLE_XPOS_PIXELS,
    OLE_YSIZE_CONTAINER, FontEvents, OLE_ENABLEDEFAULTBOOL,
    OLE_YPOS_PIXELS, DISPPARAMS, Color, OLE_XSIZE_CONTAINER,
    typelib_path, OLE_XSIZE_PIXELS, IEnumVARIANT, Monochrome, Font,
    Library, FONTSIZE, VgaColor, Default, FONTITALIC,
    OLE_YPOS_HIMETRIC, HRESULT, Picture, COMMETHOD, IDispatch, dispid,
    DISPMETHOD, OLE_YPOS_CONTAINER, OLE_XPOS_HIMETRIC, Checked,
    _check_version, VARIANT_BOOL, IFont
)


class LoadPictureConstants(IntFlag):
    Default = 0
    Monochrome = 1
    VgaColor = 2
    Color = 4


class OLE_TRISTATE(IntFlag):
    Unchecked = 0
    Checked = 1
    Gray = 2


__all__ = [
    'OLE_XSIZE_HIMETRIC', 'IFontDisp', 'Gray', 'OLE_XPOS_PIXELS',
    'OLE_YSIZE_CONTAINER', 'FontEvents', 'OLE_ENABLEDEFAULTBOOL',
    'OLE_XPOS_CONTAINER', 'OLE_YPOS_PIXELS', 'FONTSTRIKETHROUGH',
    'Color', 'OLE_YSIZE_HIMETRIC', 'OLE_COLOR', 'OLE_XSIZE_CONTAINER',
    'typelib_path', 'OLE_XSIZE_PIXELS', 'IPictureDisp', 'StdPicture',
    'OLE_HANDLE', 'Monochrome', 'Font', 'Library', 'FONTSIZE',
    'VgaColor', 'FONTBOLD', 'IFontEventsDisp', 'OLE_TRISTATE',
    'Default', 'OLE_YSIZE_PIXELS', 'FONTITALIC', 'OLE_YPOS_HIMETRIC',
    'StdFont', 'Picture', 'OLE_OPTEXCLUSIVE', 'FONTNAME', 'Unchecked',
    'OLE_YPOS_CONTAINER', 'OLE_XPOS_HIMETRIC', 'FONTUNDERSCORE',
    'Checked', 'LoadPictureConstants', 'OLE_CANCELBOOL', 'IFont',
    'IPicture'
]

