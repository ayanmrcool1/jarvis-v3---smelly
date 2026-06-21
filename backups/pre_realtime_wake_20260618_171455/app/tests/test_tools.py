from tools.system_tools import (
    get_current_datetime,
    open_application,
    search_web,
    run_terminal_command,
    get_system_stats,
    set_volume,
)


print("\nTesting current date/time...")
print(get_current_datetime())

print("\nTesting system stats...")
print(get_system_stats())

print("\nTesting terminal command...")
print(run_terminal_command("echo Jarvis tools are online"))

print("\nTesting web search...")
print(search_web("Nasdaq futures"))

print("\nTesting app opening...")
print(open_application("notepad"))

print("\nTesting volume down...")
print(set_volume("down"))

print("\nTesting volume up...")
print(set_volume("up"))