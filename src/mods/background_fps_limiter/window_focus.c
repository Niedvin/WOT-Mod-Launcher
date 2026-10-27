#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <windows.h>

static PyObject *is_focused(PyObject *self, PyObject *args)
{
    HWND window = GetForegroundWindow();
    DWORD process_id = 0;
    if (window == NULL || GetWindowThreadProcessId(window, &process_id) == 0)
        return PyBool_FromLong(1);
    return PyBool_FromLong(process_id == GetCurrentProcessId() && !IsIconic(window));
}

static PyMethodDef methods[] = {
    {"is_focused", is_focused, METH_NOARGS, NULL},
    {NULL, NULL, 0, NULL}
};

PyMODINIT_FUNC init_ua_window_focus(void)
{
    Py_InitModule("_ua_window_focus", methods);
}
