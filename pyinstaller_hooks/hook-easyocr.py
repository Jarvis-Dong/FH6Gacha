"""Package only the EasyOCR data used by FH6 price recognition."""

from PyInstaller.utils.hooks import collect_data_files

hiddenimports = ["easyocr.model.vgg_model", "easyocr.model.model"]
datas = collect_data_files(
    "easyocr",
    include_py_files=False,
    subdir="character",
    includes=["en_char.txt"],
)
