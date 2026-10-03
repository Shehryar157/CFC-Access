/*
 * CFC Access loader: a proxy dinput8.dll.
 *
 * Windows looks for DLLs in the game's folder before System32, so the game
 * loads this file instead of the real dinput8.dll. We:
 *   1. forward every dinput8 function to the real DLL in System32, so the
 *      game's input works as normal;
 *   2. start the mod (the command line in CFCAccess.txt, next to this DLL)
 *      as a separate, windowless process.
 *
 * Build: python tools/build_loader.py
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static HMODULE self;       /* this DLL */
static HMODULE real;       /* System32\dinput8.dll */
static wchar_t dir[MAX_PATH]; /* folder this DLL is in (the game folder) */

static void log_line(const char *text)
{
    wchar_t path[MAX_PATH];
    lstrcpyW(path, dir);
    lstrcatW(path, L"\\CFCAccess_loader.log");
    HANDLE f = CreateFileW(path, GENERIC_WRITE, FILE_SHARE_READ, NULL,
                           CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (f == INVALID_HANDLE_VALUE)
        return;
    DWORD written;
    WriteFile(f, text, lstrlenA(text), &written, NULL);
    CloseHandle(f);
}

/* ---- 1. Forwarding to the real dinput8.dll ---- */

static FARPROC real_proc(const char *name)
{
    if (!real) {
        wchar_t path[MAX_PATH];
        UINT n = GetSystemDirectoryW(path, MAX_PATH);
        lstrcpyW(path + n, L"\\dinput8.dll");
        real = LoadLibraryW(path);
    }
    return real ? GetProcAddress(real, name) : NULL;
}

typedef HRESULT (WINAPI *Create_t)(HINSTANCE, DWORD, const void *, void **, void *);
typedef HRESULT (WINAPI *NoArgs_t)(void);
typedef HRESULT (WINAPI *GetClass_t)(const void *, const void *, void **);

HRESULT WINAPI Proxy_DirectInput8Create(HINSTANCE inst, DWORD version, const void *iid,
                                        void **out, void *outer)
{
    Create_t f = (Create_t)real_proc("DirectInput8Create");
    return f ? f(inst, version, iid, out, outer) : E_FAIL;
}

HRESULT WINAPI Proxy_DllCanUnloadNow(void)
{
    NoArgs_t f = (NoArgs_t)real_proc("DllCanUnloadNow");
    return f ? f() : S_FALSE;
}

HRESULT WINAPI Proxy_DllGetClassObject(const void *clsid, const void *iid, void **out)
{
    GetClass_t f = (GetClass_t)real_proc("DllGetClassObject");
    return f ? f(clsid, iid, out) : E_FAIL;
}

HRESULT WINAPI Proxy_DllRegisterServer(void)
{
    NoArgs_t f = (NoArgs_t)real_proc("DllRegisterServer");
    return f ? f() : E_FAIL;
}

HRESULT WINAPI Proxy_DllUnregisterServer(void)
{
    NoArgs_t f = (NoArgs_t)real_proc("DllUnregisterServer");
    return f ? f() : E_FAIL;
}

typedef const void *(WINAPI *GetFormat_t)(void);

const void *WINAPI Proxy_GetdfDIJoystick(void)
{
    GetFormat_t f = (GetFormat_t)real_proc("GetdfDIJoystick");
    return f ? f() : NULL;
}

/* ---- 2. Starting the mod ---- */

static DWORD WINAPI start_mod(void *unused)
{
    (void)unused;
    wchar_t cfg[MAX_PATH];
    lstrcpyW(cfg, dir);
    lstrcatW(cfg, L"\\CFCAccess.txt");

    /* Read the first line of CFCAccess.txt (UTF-8). */
    char buf[2048];
    DWORD got = 0;
    HANDLE f = CreateFileW(cfg, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
    if (f == INVALID_HANDLE_VALUE) {
        log_line("CFCAccess.txt not found; mod not started\r\n");
        return 0;
    }
    ReadFile(f, buf, sizeof buf - 1, &got, NULL);
    CloseHandle(f);
    buf[got] = 0;
    char *line = buf;
    if ((unsigned char)line[0] == 0xEF && (unsigned char)line[1] == 0xBB && (unsigned char)line[2] == 0xBF)
        line += 3; /* skip a UTF-8 byte order mark */
    for (char *p = line; *p; p++)
        if (*p == '\r' || *p == '\n') { *p = 0; break; }

    wchar_t cmd[2048];
    if (!MultiByteToWideChar(CP_UTF8, 0, line, -1, cmd, 2048)) {
        log_line("CFCAccess.txt could not be read as UTF-8\r\n");
        return 0;
    }

    STARTUPINFOW si = { sizeof si };
    PROCESS_INFORMATION pi;
    if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, dir, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        log_line("mod started\r\n");
    } else {
        log_line("could not start the command in CFCAccess.txt\r\n");
    }
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE inst, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        self = inst;
        DisableThreadLibraryCalls(inst);
        GetModuleFileNameW(inst, dir, MAX_PATH);
        for (int i = lstrlenW(dir) - 1; i >= 0; i--)
            if (dir[i] == L'\\') { dir[i] = 0; break; }
        /* Windows holds the loader lock during DllMain, so starting a
         * process here could deadlock. A new thread runs once it's free. */
        HANDLE t = CreateThread(NULL, 0, start_mod, NULL, 0, NULL);
        if (t)
            CloseHandle(t);
    }
    return TRUE;
}
