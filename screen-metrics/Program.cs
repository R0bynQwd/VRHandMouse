using System.Runtime.InteropServices;

internal static class Program
{
    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int nIndex);

    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out POINT point);

    [DllImport("user32.dll")]
    private static extern nint MonitorFromPoint(POINT point, uint flags);

    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    private static extern bool GetMonitorInfo(nint monitor, ref MONITORINFOEX info);

    private const uint MONITOR_DEFAULTTONEAREST = 2;

    [StructLayout(LayoutKind.Sequential)]
    private struct POINT
    {
        public int X;
        public int Y;
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Auto)]
    private struct MONITORINFOEX
    {
        public int cbSize;
        public int rcMonitorLeft;
        public int rcMonitorTop;
        public int rcMonitorRight;
        public int rcMonitorBottom;
        public int rcWorkLeft;
        public int rcWorkTop;
        public int rcWorkRight;
        public int rcWorkBottom;
        public int dwFlags;

        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)]
        public string szDevice;
    }

    private static void Main()
    {
        GetCursorPos(out var cursor);
        var monitor = MonitorFromPoint(cursor, MONITOR_DEFAULTTONEAREST);
        var info = new MONITORINFOEX { cbSize = Marshal.SizeOf<MONITORINFOEX>() };
        GetMonitorInfo(monitor, ref info);

        Console.WriteLine($"Cursor: {cursor.X},{cursor.Y}");
        Console.WriteLine($"Primary GetSystemMetrics: {GetSystemMetrics(0)}x{GetSystemMetrics(1)}");
        Console.WriteLine($"Virtual GetSystemMetrics: {GetSystemMetrics(78)}x{GetSystemMetrics(79)} @ {GetSystemMetrics(76)},{GetSystemMetrics(77)}");
        Console.WriteLine($"Monitor device: {info.szDevice}");
        Console.WriteLine($"Monitor bounds: {info.rcMonitorLeft},{info.rcMonitorTop} -> {info.rcMonitorRight},{info.rcMonitorBottom} ({info.rcMonitorRight - info.rcMonitorLeft}x{info.rcMonitorBottom - info.rcMonitorTop})");
        Console.WriteLine($"Work area: {info.rcWorkLeft},{info.rcWorkTop} -> {info.rcWorkRight},{info.rcWorkBottom} ({info.rcWorkRight - info.rcWorkLeft}x{info.rcWorkBottom - info.rcWorkTop})");
    }
}
