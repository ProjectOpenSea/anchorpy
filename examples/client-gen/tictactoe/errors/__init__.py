from typing import Union, Optional, Any
import re
from .program_id import PROGRAM_ID
from . import anchor
from . import custom
def from_code(code: int) -> Union[custom.CustomError,anchor.AnchorError,None]:
    return custom.from_code(code) if code >= 6000 else anchor.from_code(code)
error_re = re.compile("Program (\w+) failed: custom program error: (\w+)")
def from_tx_error(error: Any) -> Optional[anchor.AnchorError]:
    if "logs" not in error:
        return None
    for logline in error["logs"]:
        first_match = error_re.match(logline)
        if first_match is not None:
            break
    if first_match is None:
        return None
    program_id_raw, code_raw = first_match.groups()
    if program_id_raw != str(PROGRAM_ID):
        return None
    try:
        error_code = int(code_raw(16))
    except ValueError:
        return None
    return from_code(error_code)