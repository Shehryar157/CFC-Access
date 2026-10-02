"""Walking another process's memory map.

A process's address space is split into regions. VirtualQueryEx describes
one region at a time (start, size, state, protection); we call it in a loop,
jumping to the end of each region, much like a generator over the map.
"""
import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

MEM_COMMIT = 0x1000
MEM_PRIVATE = 0x20000
MEM_IMAGE = 0x1000000
PAGE_GUARD = 0x100
PAGE_NOACCESS = 0x01
WRITABLE = 0x04 | 0x08 | 0x40 | 0x80  # READWRITE, WRITECOPY, EXECUTE_READWRITE, EXECUTE_WRITECOPY


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", ctypes.c_uint64),
        ("AllocationBase", ctypes.c_uint64),
        ("AllocationProtect", wintypes.DWORD),
        ("PartitionId", wintypes.WORD),
        ("RegionSize", ctypes.c_uint64),
        ("State", wintypes.DWORD),
        ("Protect", wintypes.DWORD),
        ("Type", wintypes.DWORD),
    ]


kernel32.VirtualQueryEx.argtypes = [wintypes.HANDLE, ctypes.c_uint64,
                                    ctypes.POINTER(MEMORY_BASIC_INFORMATION), ctypes.c_size_t]
kernel32.VirtualQueryEx.restype = ctypes.c_size_t


def regions(handle, writable_only=True):
    """Yield (start, size, mbi) for each committed, readable region."""
    address = 0
    mbi = MEMORY_BASIC_INFORMATION()
    while address < 0x7FFFFFFFFFFF:
        if not kernel32.VirtualQueryEx(handle, address, ctypes.byref(mbi), ctypes.sizeof(mbi)):
            break
        start, size = mbi.BaseAddress, mbi.RegionSize
        if (mbi.State == MEM_COMMIT
                and not mbi.Protect & (PAGE_GUARD | PAGE_NOACCESS)
                and mbi.Type in (MEM_PRIVATE, MEM_IMAGE)
                and (not writable_only or mbi.Protect & WRITABLE)):
            yield start, size, mbi
        address = start + size
