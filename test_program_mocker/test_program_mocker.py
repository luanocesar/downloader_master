import tkinter as tk
from tkinter import scrolledtext
import random
import time

class PCBSlot:
    def __init__(self, parent, index):
        self.index = index
        self.is_testing = False
        
        # Setup Frame for the slot
        self.frame = tk.Frame(parent, borderwidth=2, relief="groove")
        self.frame.grid(row=index//4, column=index%4, padx=5, pady=5, sticky="nsew")

        # Status Label
        self.status_lbl = tk.Label(
            self.frame, text=f"Slot {index+1} - IDLE", 
            bg="lightgray", font=("Arial", 12, "bold")
        )
        self.status_lbl.pack(fill="x", pady=2)

        # Input Entry
        self.entry = tk.Entry(self.frame, font=("Arial", 12), justify="center")
        self.entry.pack(fill="x", padx=5, pady=5)
        self.entry.insert(0, f"Enter SN for Slot {index+1}")
        self.entry.bind("<FocusIn>", self.clear_placeholder)
        self.entry.bind("<Return>", self.start_test)

        # Start Button (below the field) -- the operator/RPA clicks this
        # after the barcode is typed in to kick off the test sequence.
        self.start_btn = tk.Button(
            self.frame, text="Start", font=("Arial", 10, "bold"), command=self.start_test,
        )
        self.start_btn.pack(fill="x", padx=5, pady=(0, 5))

        # Log Area
        self.log_area = scrolledtext.ScrolledText(self.frame, wrap=tk.WORD, font=("Consolas", 9))
        self.log_area.pack(padx=5, pady=5, fill="both", expand=True)
        self.log_area.insert(tk.END, "Awaiting input...\n")
        self.log_area.config(state="disabled")

    def clear_placeholder(self, event):
        if self.entry.get().startswith("Enter SN"):
            self.entry.delete(0, tk.END)

    def start_test(self, event=None):
        sn = self.entry.get().strip()
        if self.is_testing or not sn or sn.startswith("Enter SN"):
            return

        self.is_testing = True
        self.entry.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.status_lbl.config(bg="gold", text=f"Slot {self.index+1} - TESTING")
        
        self.log_area.config(state="normal")
        self.log_area.delete(1.0, tk.END)
        self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] STARTING TEST FOR SN: {sn}\n")
        self.log_area.config(state="disabled")
        
        self.current_step = 0
        self.run_mock_sequence()

    def run_mock_sequence(self):
        # Fake PCB testing log lines
        steps = [
            "Initializing JTAG interface... OK",
            "Checking power rails (3.3V, 5V, 12V)... OK",
            "Measuring VCC to GND resistance... 15kOhm (PASS)",
            f"Reading EEPROM MAC Address... 00:1A:2B:3C:{random.randint(10,99)}:{random.randint(10,99)}",
            "Erasing flash memory... done",
            "Flashing firmware v2.4.1... 25%",
            "Flashing firmware v2.4.1... 75%",
            "Flashing firmware v2.4.1... 100% OK",
            f"Verifying checksum... 0x{random.randint(1000, 9999)}A{random.randint(10, 99)} (MATCH)",
            "Testing GPIO pins 1 through 16... OK",
            "Running RAM self-test pattern... PASS",
            "Calibrating RF transceiver frequencies... OK",
        ]

        self.log_area.config(state="normal")
        
        if self.current_step < len(steps):
            # Append next step
            self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] {steps[self.current_step]}\n")
            self.log_area.see(tk.END)
            self.current_step += 1
            
            # Schedule next step with random delay (100ms to 600ms)
            self.frame.after(random.randint(100, 600), self.run_mock_sequence)
        else:
            # Finish testing
            result = random.choices(["PASS", "FAIL"], weights=[0.85, 0.15])[0]
            self.log_area.insert(tk.END, f"[{time.strftime('%H:%M:%S')}] Finalizing sequence... {result}\n")
            self.log_area.see(tk.END)
            self.log_area.config(state="disabled")
            
            color = "lightgreen" if result == "PASS" else "salmon"
            self.status_lbl.config(bg=color, text=f"Slot {self.index+1} - {result}")

            # Deliberately left populated (not cleared) so a real-world/RPA
            # stress test can visually confirm which SN actually landed in
            # which slot's field.
            self.entry.config(state="normal")
            self.start_btn.config(state="normal")
            self.is_testing = False

class PCBTesterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("PCB Tester Mockup v2.0")
        self.root.geometry("1400x700")

        # Configure 2x4 Grid scaling
        for i in range(2):
            self.root.grid_rowconfigure(i, weight=1)
        for i in range(4):
            self.root.grid_columnconfigure(i, weight=1)

        self.slots = [PCBSlot(root, i) for i in range(8)]

if __name__ == "__main__":
    root = tk.Tk()
    app = PCBTesterApp(root)
    root.mainloop()