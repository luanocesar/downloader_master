import os
import tkinter as tk
from tkinter import messagebox, ttk

from infra.process_supervisor import ProcessSupervisor

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
    def __init__(self, base_dir, config_filename="config.json"):
        super().__init__()
        self.title("Downloader App - Configuration Manager")
        self.geometry("660x700")
        self.minsize(600, 520)
        self.config_filename = config_filename

        self._int_vcmd = (self.register(ui.validate_integer_input), "%P")

        self.supervisor = ProcessSupervisor(base_dir, ready_marker="uvicorn running on")
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

        self.settings_tab = SettingsTab(self.notebook, request_silent_save=lambda: self.save_config(silent=True))
        self.notebook.add(self.settings_tab, text="Server Settings")

        self.auto_script_tab = AutoScriptTab(
            self.notebook, self._int_vcmd,
            get_target_window_title=self.settings_tab.get_target_window_title,
            request_silent_save=lambda: self.save_config(silent=True),
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

        filename = self.settings_tab.get_main_process_file()

        try:
            target_path = self.supervisor.start(filename)
        except FileNotFoundError as e:
            messagebox.showerror(
                "Error",
                f"Main process file not found:\n{e}\n\n"
                "Check 'Main Process File' in Server Settings.",
            )
            return
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start {filename}:\n{str(e)}")
            return

        self.settings_tab.append_console_line(
            f"--- Started {os.path.basename(target_path)} (PID {self.supervisor.pid}) ---"
        )
        self._locked = True
        self._apply_states()

    def _on_stop_clicked(self):
        if not self.supervisor.is_running or self.supervisor.stopping:
            return

        # Don't flip to OFF / unlock right away: on Windows, terminating a
        # process doesn't guarantee its listening socket is released
        # immediately. If the user hits Start again too fast, the new
        # process can fail to bind with "only one usage of each socket
        # address is normally permitted". Stay locked (status shows
        # STOPPING...) until _poll_process confirms the process has
        # actually exited.
        self.settings_tab.append_console_line(f"--- Stopping process (PID {self.supervisor.pid}) ---")
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
        self.log_file_tab.set_locked(self._locked)
        self.btn_reload.configure(state="disabled" if self._locked else "normal")

        self._update_run_controls()

    def on_closing(self):
        self.supervisor.force_kill()
        self.destroy()

    # --- JSON STORAGE ---
    def _collect_settings_payload(self):
        payload = {}
        payload.update(self.settings_tab.get_payload())
        payload.update(self.log_file_tab.get_payload())
        payload.update(self.auto_script_tab.get_payload())
        return payload

    def load_config(self):
        try:
            data = config_editor.load(self.config_filename)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load JSON:\n{str(e)}")
            return

        self.settings_tab.apply_data(data)
        self.log_file_tab.apply_data(data)
        self.auto_script_tab.apply_data(data.get("SLOTS", {}))

        # Baseline for dirty-tracking: whatever is on disk right now counts
        # as "saved", so Save starts disabled until the user actually changes something.
        self._last_saved_payload = self._collect_settings_payload()
        self._dirty = False

        self._apply_states()

    def save_config(self, silent=False):
        if not self.log_file_tab.validate():
            return

        try:
            payload = self._collect_settings_payload()
            config_editor.save(self.config_filename, payload)

            self._last_saved_payload = payload
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
