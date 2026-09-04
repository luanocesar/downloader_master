import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from api.server import create_app
from core.config import load_and_validate_config
from infra.server_supervisor import ServerSupervisor

from . import config_editor
from . import tk_helpers as ui
from .auto_script_tab import AutoScriptTab
from .log_file_tab import LogFileTab
from .settings_tab import SettingsTab

STOP_ACTIVE_BG = "#e57373"
STOP_INACTIVE_BG = "#fbe4e4"
STATUS_ON_BG = "#00e5ff"
STATUS_OFF_BG = "#cfd8dc"


class SetupApp(tk.Tk):
    def __init__(self, config_filename="config.json"):
        super().__init__()
        self.geometry("660x700")
        self.minsize(600, 520)
        self.config_filename = config_filename
        # Placeholder until load_config() reads the real pointer from
        # config.json's SCRIPT_FILE -- AutoScriptTab needs a value to display
        # immediately when it's built, before the first load_config() runs.
        self.script_filename = self._default_script_path()
        self._update_title()

        self._int_vcmd = (self.register(ui.validate_integer_input), "%P")

        self.supervisor = ServerSupervisor(ready_marker="uvicorn running on")
        self._locked = False
        self._dirty = False
        self._last_saved_payload = None

        self._init_ui()
        self.load_config()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.after(150, self._poll_process)
        self.after(300, self._poll_dirty_state)

    def _init_ui(self):
        # --- NOTEBOOK ---
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=4)

        self.settings_tab = SettingsTab(
            self.notebook, request_silent_save=lambda: self.save_config(silent=True),
            on_use_log_file_toggle=self._on_use_log_file_toggle,
        )
        self.notebook.add(self.settings_tab, text="Server Settings")

        self.auto_script_tab = AutoScriptTab(
            self.notebook, self._int_vcmd,
            get_target_window_title=self.settings_tab.get_target_window_title,
            get_active_script_name=self._active_script_name,
            on_open_script=self._open_script_dialog,
            on_save_as_script=self._save_script_as_dialog,
        )
        self.notebook.add(self.auto_script_tab, text="Auto Script")

        self.log_file_tab = LogFileTab(self.notebook, self._int_vcmd)
        self.notebook.add(self.log_file_tab, text="Log File")

        # --- FOOTER ---
        footer = ttk.Frame(self)
        footer.pack(fill="x", side="bottom", padx=8, pady=6)

        self.btn_start = tk.Button(
            footer, text="Start", font=("Segoe UI", 11, "bold"), width=8, bd=2,
            relief="raised", highlightthickness=0, command=self._on_start_clicked,
        )
        self.btn_start.pack(side="left")

        self.btn_stop = tk.Button(
            footer, text="Stop", font=("Segoe UI", 11, "bold"), width=8, bd=2,
            relief="raised", highlightthickness=0, command=self._on_stop_clicked,
        )
        self.btn_stop.pack(side="left", padx=(1, 0))

        self.status_label = tk.Label(
            footer, text="OFF", font=("Segoe UI", 11, "bold"), width=16, bd=2,
            relief="sunken", highlightthickness=0, pady=4,
        )
        self.status_label.pack(side="left", padx=(1, 0))

        self.btn_save = ttk.Button(footer, text="Save", command=self.save_config)
        self.btn_save.pack(side="right")

        self.btn_reload = ttk.Button(footer, text="Reload", command=self.load_config)
        self.btn_reload.pack(side="right", padx=(0, 1))

    # --- SERVER CONTROL ---
    def _on_start_clicked(self):
        if self.supervisor.is_running:
            return

        try:
            server_config = load_and_validate_config(self.config_filename, self.script_filename)
        except FileNotFoundError as e:
            messagebox.showerror("Error", f"Config or script file not found:\n{e}")
            return
        except Exception as e:
            messagebox.showerror("Error", f"Invalid configuration in {self.config_filename} / {self.script_filename}:\n{str(e)}")
            return

        app = create_app(server_config, self.config_filename, self.script_filename)
        self.supervisor.start(app, server_config.host, server_config.port)

        self.settings_tab.append_console_line("--- Starting server ---")
        self._locked = True
        self._apply_states()

    def _on_stop_clicked(self):
        if not self.supervisor.is_running or self.supervisor.stopping:
            return

        # Don't flip to OFF / unlock right away: should_exit is only honored
        # on the next iteration of uvicorn's event loop, not instantly. Stay
        # locked (status shows STOPPING...) until _poll_process confirms the
        # server thread has actually finished.
        self.settings_tab.append_console_line("--- Stopping server ---")
        self.supervisor.stop()
        self._update_run_controls()

    def _poll_process(self):
        for line in self.supervisor.poll():
            self.settings_tab.append_console_line(line)

        if self._locked and not self.supervisor.is_running and not self.supervisor.stopping:
            # Process exited on its own, or a requested stop just finished.
            self._locked = False
            self._apply_states()
        else:
            self._update_run_controls()

        self.after(150, self._poll_process)

    # --- DIRTY / SAVE STATE ---
    def _poll_dirty_state(self):
        try:
            current = self._collect_settings_payload()
            dirty = current != self._last_saved_payload
        except Exception:
            # Mid-edit invalid input (e.g. PORT momentarily empty) still
            # counts as "not matching what's saved on disk".
            dirty = True

        if dirty != self._dirty:
            self._dirty = dirty
            self._update_run_controls()

        self.after(300, self._poll_dirty_state)

    def _update_run_controls(self):
        """Drives the Start/Stop pushbutton pair and the ON/OFF status light
        from the current run state, plus the Save button from dirty state.

        Start/Stop behave like a two-position control-panel switch: whichever
        one reflects the CURRENT status appears pressed (sunken) and is
        disabled (nothing to do by pressing it again); the other is
        unpressed (raised) and, if applicable, enabled. Only Stop carries
        color (salmon, saturated when pressed / pale when not) -- Start
        stays neutral and communicates its state through relief alone.
        """
        running = self.supervisor.is_running
        can_edit = not self._locked

        self.btn_save.configure(state="normal" if (self._dirty and can_edit) else "disabled")

        if self.supervisor.stopping:
            start_pressed, start_enabled = False, False
            stop_pressed, stop_enabled = True, False
            status_text, status_bg, status_fg = "STOPPING...", STATUS_OFF_BG, "black"
        elif running and self.supervisor.confirmed_running:
            start_pressed, start_enabled = True, False
            stop_pressed, stop_enabled = False, True
            status_text, status_bg, status_fg = "ON", STATUS_ON_BG, "black"
        elif running:  # process spawned, waiting for uvicorn's own confirmation
            start_pressed, start_enabled = True, False
            stop_pressed, stop_enabled = False, True
            status_text, status_bg, status_fg = "STARTING...", STATUS_OFF_BG, "black"
        else:  # fully stopped
            start_pressed, start_enabled = False, (not self._dirty) and can_edit
            stop_pressed, stop_enabled = True, False
            status_text, status_bg, status_fg = "OFF", STATUS_OFF_BG, "black"

        self.btn_start.configure(
            relief="sunken" if start_pressed else "raised",
            state="normal" if start_enabled else "disabled",
        )
        self.btn_stop.configure(
            bg=STOP_ACTIVE_BG if stop_pressed else STOP_INACTIVE_BG,
            relief="sunken" if stop_pressed else "raised",
            state="normal" if stop_enabled else "disabled",
        )
        self.status_label.configure(text=status_text, bg=status_bg, fg=status_fg)

    def _apply_states(self):
        """Recomputes the enabled/disabled state of every tab based on
        whether the server is running (locked); each tab further cascades
        that into its own Slot/Action-level enabled checkboxes."""
        self.settings_tab.set_locked(self._locked)
        self.auto_script_tab.set_locked(self._locked)
        self._apply_log_file_tab_state()
        self.btn_reload.configure(state="disabled" if self._locked else "normal")

        self._update_run_controls()

    def _apply_log_file_tab_state(self):
        # The Log File tab is only meaningful when "Use Log File Logic" is
        # checked on Server Settings; keep it greyed out otherwise, on top of
        # the usual running-server lock.
        self.log_file_tab.set_locked(self._locked or not self.settings_tab.get_use_log_file())

    def _on_use_log_file_toggle(self, _enabled):
        self._apply_log_file_tab_state()

    def on_closing(self):
        self.supervisor.force_kill()
        self.destroy()

    # --- JSON STORAGE ---
    # Split across two files: config.json (fixed name, server settings + the
    # SCRIPT_FILE pointer) and the script file (SLOTS/Actions), whose name the
    # user picks per model/line via Open/Save As. Keeping the pointer in
    # config.json is what lets a restart resume on the right script instead
    # of always falling back to a default.
    def _collect_app_payload(self):
        payload = {}
        payload.update(self.settings_tab.get_payload())
        payload.update(self.log_file_tab.get_payload())
        payload["SCRIPT_FILE"] = self.script_filename
        return payload

    def _collect_script_payload(self):
        return self.auto_script_tab.get_payload()

    def _collect_settings_payload(self):
        # Combined snapshot used only for dirty-tracking equality checks.
        payload = {}
        payload.update(self._collect_app_payload())
        payload.update(self._collect_script_payload())
        return payload

    def load_config(self):
        """Returns True on success, False if a dialog was shown and the
        in-memory/on-disk state was left untouched -- callers that chain a
        disk write (switching the active script) must check this before
        persisting, so a bad pick doesn't become the new sticky default."""
        try:
            app_data = config_editor.load_app_config(self.config_filename)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load config JSON:\n{str(e)}")
            return False

        self.script_filename = app_data.get("SCRIPT_FILE") or self._default_script_path()

        try:
            script_data = config_editor.load_script_config(self.script_filename)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load script JSON:\n{str(e)}")
            return False

        self.settings_tab.apply_data(app_data)
        self.log_file_tab.apply_data(app_data)
        self.auto_script_tab.apply_data(script_data)

        # Baseline for dirty-tracking: whatever is on disk right now counts
        # as "saved", so Save starts disabled until the user actually changes something.
        self._last_saved_payload = self._collect_settings_payload()
        self._dirty = False

        self._update_title()
        self.auto_script_tab.refresh_script_display()
        self._apply_states()
        return True

    def save_config(self, silent=False):
        # Silent saves (window-picker confirm, coordinate capture) persist a
        # single already-known-valid field in the background and must never
        # block on or pop a dialog about an unrelated, possibly-unfinished
        # tab -- only the explicit Save button enforces full validity. The Log
        # File tab is optional: only validate it if the user opted into it.
        use_log_file = self.settings_tab.get_use_log_file()
        if not silent and use_log_file and not self.log_file_tab.validate():
            return

        try:
            app_payload = self._collect_app_payload()
            script_payload = self._collect_script_payload()
            config_editor.save(self.config_filename, app_payload)
            config_editor.save(self.script_filename, script_payload)

            self._last_saved_payload = {**app_payload, **script_payload}
            self._dirty = False
            self._update_run_controls()

            if not silent:
                messagebox.showinfo("Success", "Configuration saved successfully!")

        except ValueError:
            if not silent:
                messagebox.showerror("Validation Error", "PORT and every Click At Coordinates X/Y must be valid integers.")
        except Exception as e:
            if not silent:
                messagebox.showerror("Save Error", f"An unexpected error occurred:\n{str(e)}")

    # --- MULTIPLE SCRIPT FILES ---
    def _update_title(self):
        self.title(f"Downloader App - Configuration Manager [{self._active_script_name()}]")

    def _config_dir(self):
        return os.path.dirname(os.path.abspath(self.config_filename)) or "."

    def _script_dir(self):
        return os.path.dirname(os.path.abspath(self.script_filename)) or "."

    def _default_script_path(self):
        return os.path.join(self._config_dir(), "scriptfile.json")

    def _active_script_name(self):
        return os.path.basename(self.script_filename)

    def _confirm_discard_if_dirty(self):
        if not self._dirty:
            return True
        return messagebox.askyesno(
            "Unsaved Changes", "You have unsaved changes. Discard them and continue?",
        )

    def _persist_script_pointer(self):
        # Best-effort: writes config.json's SCRIPT_FILE so the next launch
        # resumes on this script. If a field is mid-edit/invalid right now,
        # the explicit Save button will pick it up properly later.
        try:
            config_editor.save(self.config_filename, self._collect_app_payload())
        except Exception:
            pass

    def _switch_script(self, path):
        if self._locked:
            messagebox.showwarning("Server Running", "Stop the server before switching script files.")
            return
        if not self._confirm_discard_if_dirty():
            return

        self.script_filename = path
        if self.load_config():
            self._persist_script_pointer()

    def _open_script_dialog(self):
        if self._locked:
            messagebox.showwarning("Server Running", "Stop the server before switching script files.")
            return

        path = filedialog.askopenfilename(
            title="Open Script File", initialdir=self._script_dir(),
            filetypes=[("JSON Script", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return

        self._switch_script(path)

    def _save_script_as_dialog(self):
        default_name = os.path.splitext(self._active_script_name())[0]
        path = filedialog.asksaveasfilename(
            title="Save Script As", initialdir=self._script_dir(),
            initialfile=f"{default_name}.json", defaultextension=".json",
            filetypes=[("JSON Script", "*.json"), ("All Files", "*.*")],
        )
        if not path:
            return

        try:
            script_payload = self._collect_script_payload()
            config_editor.save(path, script_payload)
        except Exception as e:
            messagebox.showerror("Save Error", f"An unexpected error occurred:\n{str(e)}")
            return

        self.script_filename = path
        self._update_title()
        self._persist_script_pointer()
        self._last_saved_payload = self._collect_settings_payload()
        self._dirty = False
        self._update_run_controls()
        messagebox.showinfo("Success", f"Saved as '{os.path.basename(path)}'.")
