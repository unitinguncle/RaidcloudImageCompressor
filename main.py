import os
import threading
import logging
import asyncio
import aiofiles
import io
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import Tk, Scale, Canvas, Entry, Text, Button, PhotoImage, StringVar, Radiobutton, Scrollbar, messagebox, filedialog
from tkinter.ttk import Progressbar, Style
from PIL import Image
from multiprocessing import Manager
from pathlib import Path
import sys
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn")

def resource_path(relative_path):
    """ Get the absolute path to a resource, works for dev and for PyInstaller """
    try:
        base_path = sys._MEIPASS  # PyInstaller creates a temp folder and stores path in _MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# Usage
ASSETS_FOLDER = resource_path("assets")

# Constants
VALID_IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.cr2', '.cr3', '.nef', '.nrw', '.arw', '.sr2', '.srf')
#ASSETS_FOLDER = "./assets/"

# Configure logging
def setup_logging(compressed_folder):
    log_file = os.path.join(compressed_folder, "compressor.log")
    logging.basicConfig(
        filename=log_file,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

# Helper function to update the queue
def update_queue(queue, message, success=True):
    queue.put((message, success))

# Standalone function for image compression with retries
async def compress_image(file_path, output_folder, output_format, jpeg_quality, png_compression, queue, max_retries=3):
    filename = os.path.basename(file_path)
    for attempt in range(max_retries):
        try:
            logging.info(f"Attempt {attempt + 1}: Processing {file_path}")
            async with aiofiles.open(file_path, mode='rb') as f:
                img_data = await f.read()

            img = Image.open(io.BytesIO(img_data))
            new_filename = os.path.splitext(filename)[0] + f"_compressed.{output_format.lower()}"
            new_file_path = os.path.join(output_folder, new_filename)

            if filename.lower().endswith(('.cr2', '.cr3', '.nef', '.nrw', '.arw', '.sr2', '.srf')):
                img = img.convert("RGB")

            save_args = {"format": output_format, "optimize": True}
            if output_format == "JPEG":
                save_args["quality"] = jpeg_quality
            elif output_format == "PNG":
                save_args["compress_level"] = png_compression

            img.save(new_file_path, **save_args)
            logging.info(f"Successfully compressed {filename}")
            update_queue(queue, f"Successfully compressed {filename}", True)
            break
        except Exception as e:
            if attempt == max_retries - 1:
                logging.error(f"Failed to process {filename}: {str(e)}")
                update_queue(queue, f"Failed to process {filename}: {str(e)}", False)
            await asyncio.sleep(2 ** attempt)

class ImageCompressorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("RaidCloud Compressor v1.0.0")
        self.root.geometry("1100x700")
        self.root.configure(bg="#141313")
        self.root.resizable(False, False)

        # Variables
        self.folder_path = StringVar()
        self.output_format = StringVar(value="JPEG")
        self.upload_to_immich = StringVar(value="no")
        self.server_address = StringVar(value="https://photos.raidcloud.in")
        self.api_key = StringVar()
        self.cancel_process = False  # Flag to cancel the compression process

        # Create Canvas
        self.canvas = Canvas(
            self.root,
            bg="#141313",
            height=700,
            width=1100,
            bd=0,
            highlightthickness=0,
            relief="ridge"
        )
        self.canvas.place(x=0, y=0)

        # Header
        self.canvas.create_rectangle(
            -3.0, 59.0, 1099.9999952285725, 64.00000001321087,
            fill="#37B4FC", outline=""
        )
        # Left top logo
        self.image_image_2 = PhotoImage(file=resource_path("assets/image_2.png"))
        self.canvas.create_image(78.0, 30.0, image=self.image_image_2)
        self.canvas.create_text(
            150.0, 21.0, anchor="nw", text="RaidCloud Image Compressor",
            fill="#FFFFFF", font=("Terminal", 24 * -1)
        )
        # Background image
        self.image_image_1 = PhotoImage(file=resource_path("assets/image_1.png"))
        self.canvas.create_image(550.0, 377.0, image=self.image_image_1)

        # Select Folder Section
        self.canvas.create_text(
            43.0, 105.0, anchor="nw", text="SELECT FOLDER :",
            fill="white", font=("Terminal", 15 * -1)
        )
        self.button_image_1 = PhotoImage(file=resource_path("assets/button_1.png"))
        self.browse_button = Button(
            image=self.button_image_1,
            borderwidth=0,
            highlightthickness=0,
            command=self.browse_folder,
            relief="flat"
        )
        self.browse_button.place(x=217.0, y=98.0, width=125.0, height=32.0)

        # Selected Folder Label
        self.selected_folder_label = self.canvas.create_text(
            217.0, 141.0, anchor="nw", text="NO FOLDER SELECTED",
            fill="#37B4FC", font=("Courier", 13 * -1)
        )

        # File Count Label
        self.file_count_label = self.canvas.create_text(
            217.0, 168.0, anchor="nw", text="0 IMAGE FILE FOUND.",
            fill="#37B4FC", font=("Courier", 13 * -1)
        )

        # Output Format Section
        self.canvas.create_text(
            43.0, 230.0, anchor="nw", text="SELECT OUTPUT FORMAT FOR RAW FILES :",
            fill="#FFFFFF", font=("Terminal", 13 * -1)
        )
        self.output_format_jpeg = Radiobutton(
            self.root, text="JPEG", variable=self.output_format, value="JPEG", font=("Courier", 13 * -1),
            bg="#141313", fg="#FFFFFF", selectcolor="#000000"
        )
        self.output_format_jpeg.place(x=129.0, y=263.0)

        self.output_format_png = Radiobutton(
            self.root, text="PNG", variable=self.output_format, value="PNG", font=("Courier", 13 * -1),
            bg="#141313", fg="#FFFFFF", selectcolor="#000000"
        )
        self.output_format_png.place(x=295.0, y=263.0)

        # JPEG Quality Slider
        self.canvas.create_text(
            577.0, 98.0, anchor="nw", text="JPEG QUALITY :",
            fill="#FFFFFF", font=("Terminal", 13 * -1)
        )
        self.jpeg_quality = Scale(
            self.root, from_=0, to=90, orient="horizontal",
            bg="#37B4FC", fg="#FFFFFF", length=350
        )
        self.jpeg_quality.set(85)  # Default value
        self.jpeg_quality.place(x=720.0, y=90.0)

        # PNG Compression Level Slider
        self.canvas.create_text(
            577.0, 160.0, anchor="nw", text="PNG COMPRESSION LEVEL :",
            fill="#FFFFFF", font=("Terminal", 13 * -1)
        )
        self.png_compression = Scale(
            self.root, from_=0, to=9, orient="horizontal",
            bg="#37B4FC", fg="#FFFFFF", length=200
        )
        self.png_compression.set(6)  # Default value
        self.png_compression.place(x=800.0, y=140.0)

        # Estimate Size Button
        self.button_image_3 = PhotoImage(file=resource_path("assets/button_3.png"))
        self.estimate_button = Button(
            image=self.button_image_3,
            borderwidth=0,
            highlightthickness=0,
            command=self.estimate_size,
            relief="flat"
        )
        self.estimate_button.place(x=577.0, y=198.0, width=435.0, height=38.0)

        # Estimated Size Label
        self.estimated_size_label = self.canvas.create_text(
            577.0, 256.0, anchor="nw", text="ESTIMATED SIZE : N/A",
            fill="#FFFFFF", font=("Terminal", 13 * -1)
        )

        # Upload to Immich Server Section
        self.canvas.create_text(
            43.0, 309.0, anchor="nw", text="DO YOU WANT TO UPLOAD TO IMMICH SERVER ?",
            fill="#FFFFFF", font=("Terminal", 13 * -1)
        )
        self.upload_yes = Radiobutton(
            self.root, text="YES", variable=self.upload_to_immich, value="yes", font=("Courier", 13 * -1),
            bg="#141313", fg="#FFFFFF", selectcolor="#000000", command=self.toggle_upload_fields
        )
        self.upload_yes.place(x=129.0, y=334.0)
        self.upload_no = Radiobutton(
            self.root, text="NO", variable=self.upload_to_immich, value="no", font=("Courier", 13 * -1),
            bg="#141313", fg="#FFFFFF", selectcolor="#000000", command=self.toggle_upload_fields
        )
        self.upload_no.place(x=296.0, y=334.0)

        # Server Address and API Key Fields
        self.server_address_text = self.canvas.create_text(
            43.0, 370.0, anchor="nw", text="Server Address : ",
            fill="#FFFFFF", font=("Terminal", 13 * -1), state="hidden"
        )
        self.server_address_entry = Entry(
            self.root, bd=1, bg="#37B4FC", fg="white", textvariable=self.server_address, highlightthickness=0, font=('courier', 13, 'bold')
        )
        self.api_key_text = self.canvas.create_text(
            43.0, 445.0, anchor="nw", text="Api Key : ",
            fill="#FFFFFF", font=("Terminal", 13 * -1), state="hidden"
        )
        self.api_key_entry = Entry(
            self.root, bd=1, bg="#37B4FC", fg="white", highlightthickness=0, font=('courier', 13, 'bold')
        )

        # Compress Images Button
        self.button_image_2 = PhotoImage(file=resource_path("assets/button_2.png"))
        self.compress_button = Button(
            image=self.button_image_2,
            borderwidth=0,
            highlightthickness=0,
            command=self.compress_images,
            relief="flat"
        )
        self.compress_button.place(x=43.0, y=625.0, width=125.0, height=32.0)

        # Cancel Button
        self.button_image_cancel = PhotoImage(file=resource_path("assets/button_cancel.png"))
        self.cancel_button = Button(
            image=self.button_image_cancel,
            borderwidth=0,
            highlightthickness=0,
            command=self.cancel_compression,
            relief="flat"
        )
        self.cancel_button.place(x=200.0, y=625.0, width=125.0, height=32.0)
        self.cancel_button.config(state="disabled")  # Disabled by default

        # View Log Button
        self.button_image_log = PhotoImage(file=resource_path("assets/button_log.png"))
        self.view_log_button = Button(
            image=self.button_image_log,
            borderwidth=0,
            highlightthickness=0,
            command=self.view_log,
            relief="flat"
        )
        self.view_log_button.place(x=350.0, y=625.0, width=125.0, height=32.0)
        self.view_log_button.config(state="disabled")  # Disabled by default

        self.canvas.create_text(
            320.0, 680.0, anchor="nw", text="DESIGNED AND DEVELOPED BY RAIDCLOUD | CONTACT US ON RAIDCLOUD@GMAIL.COM",
            fill="#FFFFFF", font=("Terminal", 11 * -1)
        )

    def browse_folder(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.folder_path.set(folder_selected)
            self.canvas.itemconfig(self.selected_folder_label, text=folder_selected)
            self.update_file_count()

    def update_file_count(self):
        folder_path = self.folder_path.get()
        if folder_path:
            image_files = [f for f in os.listdir(folder_path) if f.lower().endswith(VALID_IMAGE_EXTENSIONS)]
            self.total_image_files = len(image_files)
            self.canvas.itemconfig(self.file_count_label, text=f"{self.total_image_files} IMAGE FILE FOUND.")

    def estimate_size(self):
        folder_path = self.folder_path.get()
        if not folder_path:
            messagebox.showerror("Error", "Please select a folder first.")
            return

        image_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith(VALID_IMAGE_EXTENSIONS)]
        total_size = 0
        jpeg_quality = self.jpeg_quality.get()
        png_compression = self.png_compression.get()

        for file_path in image_files:
            original_size = os.path.getsize(file_path)
            if file_path.lower().endswith(('.jpg', '.jpeg')):
                estimated_size = original_size * (jpeg_quality / 100)
            elif file_path.lower().endswith('.png'):
                compression_factor = 1.0 - (0.03 * png_compression)
                estimated_size = original_size * compression_factor
            else:
                estimated_size = original_size

            total_size += estimated_size

        total_original_size = sum(os.path.getsize(f) for f in image_files)
        avg_original_size = total_original_size / len(image_files) if image_files else 0
        avg_size = total_size / len(image_files) if image_files else 0

        self.canvas.itemconfig(self.estimated_size_label, text=f"Total Original size: {total_original_size / (1024 * 1024):.2f} MB\nOriginal Average file size: {avg_original_size / 1024:.2f} KB \n\nEstimated size after compression: {total_size / (1024 * 1024):.2f} MB\nAverage compressed file size: {avg_size / 1024:.2f} KB")

    def toggle_upload_fields(self):
        if self.upload_to_immich.get() == "yes":
            self.canvas.itemconfig(self.server_address_text, state="normal")
            self.canvas.itemconfig(self.api_key_text, state="normal")
            self.server_address_entry.place(x=40.0, y=386.0, width=325.0, height=35.0)
            self.api_key_entry.place(x=40.0, y=462.0, width=325.0, height=35.0)
        else:
            self.canvas.itemconfig(self.server_address_text, state="hidden")
            self.canvas.itemconfig(self.api_key_text, state="hidden")
            self.server_address_entry.place_forget()
            self.api_key_entry.place_forget()

    def compress_images(self):
        folder_path = self.folder_path.get()
        if not folder_path:
            messagebox.showerror("Error", "Please select a folder first.")
            return

        self.server_address.set(self.server_address_entry.get())
        self.api_key.set(self.api_key_entry.get())

        if self.upload_to_immich.get() == "yes":
            server_address = self.server_address.get()
            api_key = self.api_key.get()

            if not server_address or not api_key:
                error_message = "Error: Please provide both server address and API key."
                messagebox.showerror("Error", error_message)
                logging.error(error_message)
                return

        compressed_folder = os.path.join(folder_path, "compressed")
        if not os.path.exists(compressed_folder):
            os.makedirs(compressed_folder)

        setup_logging(compressed_folder)

        self.processing_label = self.canvas.create_text(
            190.0, 581.0, anchor="nw", text=f"PROCESSING FILE - 0/{self.total_image_files}",
            fill="#FFFFFF", font=("Terminal", 13 * -1)
        )

        self.message_area = Text(
            self.root, bd=0, bg="black", fg="#37B4FC", highlightthickness=0, font=('courier', 11, 'normal')
        )
        self.message_area.place(x=576.0, y=350.0, width=456.0, height=248.0)
        scrollbar = Scrollbar(self.root, command=self.message_area.yview)
        scrollbar.place(x=1032.0, y=350.0, height=248.0)
        self.message_area.config(yscrollcommand=scrollbar.set, state="normal")

        self.progress = Progressbar(
            self.root, orient="horizontal", length=456, mode="determinate",
        )
        self.progress.place(x=576.0, y=627.0, width=456.0, height=33.0)
        style = Style()
        style.configure("Horizontal.TProgressbar", foreground="#37B4FC", background="#000000")
        self.progress.configure(style="Horizontal.TProgressbar")

        # Enable Cancel Button and Disable Compress Button
        self.cancel_button.config(state="normal")
        self.compress_button.config(state="disabled")

        # Create a Manager for shared objects
        manager = Manager()
        self.queue = manager.Queue(maxsize=100)  # Shared queue with size limit

        # Start the GUI update thread
        threading.Thread(target=self.update_gui_from_queue, daemon=True).start()

        # Start the multiprocessing task in a separate thread
        self.cancel_process = False  # Reset cancel flag
        threading.Thread(
            target=self.process_images,
            args=(folder_path, compressed_folder, self.queue),
            daemon=True
        ).start()

    def process_images(self, folder_path, compressed_folder, queue):
        if __name__ == "__main__":
            output_format = self.output_format.get()
            jpeg_quality = self.jpeg_quality.get()
            png_compression = self.png_compression.get()

            # Get list of image files (excluding immich-go.exe)
            image_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.lower().endswith(VALID_IMAGE_EXTENSIONS) and f.lower() != "immich-go.exe"]

            # Sort images by size (largest first)
            image_files.sort(key=lambda x: os.path.getsize(x), reverse=True)

            # Dynamically determine the number of threads
            num_threads = min(os.cpu_count() or 1, 32)  # Use CPU count, but cap at 32 threads

            # Process images using ThreadPoolExecutor
            total_images = len(image_files)
            with ThreadPoolExecutor(max_workers=num_threads) as executor:
                futures = []
                for i, file_path in enumerate(image_files):
                    if self.cancel_process:  # Check if the process was canceled
                        update_queue(queue, "Compression process canceled by user.", False)
                        break

                    futures.append(
                        executor.submit(
                            asyncio.run,
                            compress_image(file_path, compressed_folder, output_format, jpeg_quality, png_compression, queue)
                        )
                    )
                    self.canvas.itemconfig(self.processing_label,text=f"Processed files - {i + 1}/{total_images}")
                    update_queue(queue, f"Analyzed files - {i + 1}/{total_images}", True)

                # Wait for all tasks to complete
                for future in as_completed(futures):
                    if self.cancel_process:  # Stop processing if canceled
                        break
                    future.result()  # Handle any exceptions

            if not self.cancel_process:
                update_queue(queue, "DONE", True)  # Signal that processing is complete

                # Upload to Immich server if requested
                if self.upload_to_immich.get() == "yes":
                    self.upload_to_immich_server(compressed_folder)

            # Re-enable Compress Button and Disable Cancel Button
            self.compress_button.config(state="normal")
            self.cancel_button.config(state="disabled")
            self.view_log_button.config(state="normal")  # Enable View Log Button
            pass

    def upload_to_immich_server(self, compressed_folder):
        server_address = self.server_address.get()
        api_key = self.api_key.get()

        if not server_address or not api_key:
            error_message = "Error: Please provide both server address and API key."
            update_queue(self.queue, error_message, False)
            messagebox.showerror("Error", error_message)
            logging.error(error_message)
            return

        # Get the path to immich-go.exe using resource_path
        immich_go_path = resource_path("immich-go.exe")
        if not os.path.exists(immich_go_path):
            error_message = f"Error: immich-go.exe not found at {immich_go_path}."
            update_queue(self.queue, error_message, False)
            messagebox.showerror("Error", error_message)
            logging.error(error_message)
            return

        # Notify GUI and log that upload is starting
        update_queue(self.queue, "Starting upload to Immich server...", True)
        logging.info("Starting upload to Immich server...")

        # Construct the absolute path to run_immich.bat
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            # Running as bundled executable
            base_path = sys._MEIPASS
        else:
            # Running as a regular Python script
            base_path = os.path.abspath(os.path.dirname(sys.argv[0]))

        batch_file_path = os.path.join(base_path, "run_immich.bat")

        # Construct the command as a list
        command = [
            batch_file_path,
            immich_go_path,
            compressed_folder,
            server_address,
            api_key
        ]

        # Log the command for debugging
        logging.info(f"Running command: {' '.join(command)}")

        try:
            # Use subprocess.Popen with the command list (shell=False)
            process = subprocess.Popen(command, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()  # Wait for the process to complete

            if process.returncode == 0:
                update_queue(self.queue, "Upload to Immich server completed successfully.", True)
                update_queue(self.queue, stdout, True)  # Display command output in the message area
                logging.info("Upload to Immich server completed successfully.")
            else:
                error_message = f"Failed to upload to Immich server: {stderr}"
                update_queue(self.queue, error_message, False)
                logging.error(error_message)
        except Exception as e:
            error_message = f"Failed to start upload to Immich server: {str(e)}"
            update_queue(self.queue, error_message, False)
            logging.error(error_message)

    def cancel_compression(self):
        self.cancel_process = True
        update_queue(self.queue, "Canceling compression process...", False)
        self.cancel_button.config(state="disabled")  # Disable Cancel Button after clicking

    def view_log(self):
        folder_path = self.folder_path.get()
        if folder_path:
            log_file = os.path.join(folder_path, "compressed", "compressor.log")
            if os.path.exists(log_file):
                try:
                    with open(log_file, "r") as f:
                        log_content = f.read()
                    self.message_area.config(state="normal")
                    self.message_area.delete(1.0, "end")
                    self.message_area.insert("end", log_content)
                    self.message_area.config(state="disabled")
                    self.message_area.yview("end")  # Auto-scroll to the bottom
                except Exception as e:
                    messagebox.showerror("Error", f"Failed to read log file: {str(e)}")
            else:
                messagebox.showinfo("Info", "No log file found.")
        else:
            messagebox.showerror("Error", "Please select a folder first.")

    def update_gui_from_queue(self):
        folder_path = self.folder_path.get()
        if folder_path:
            total_files = len([f for f in os.listdir(folder_path) if f.lower().endswith(VALID_IMAGE_EXTENSIONS) and f.lower() != "immich-go.exe"])
        else:
            total_files = 0

        processed_files = 0
        while True:
            try:
                message, success = self.queue.get(timeout=1)  # Add a timeout to avoid blocking indefinitely

                if total_files == 0:
                    self.message_area.config(state="normal")
                    self.message_area.insert("end", "No images to compress and upload found!")
                    self.message_area.config(state="disabled")
                    self.message_area.yview("end")  # Auto-scroll to the bottom
                    break

                if message == "DONE":
                    self.message_area.config(state="normal")
                    self.message_area.insert("end", f"All files were compressed successfully in the directory: {self.folder_path.get()}\n")
                    self.message_area.config(state="disabled")
                    self.message_area.yview("end")  # Auto-scroll to the bottom
                    break
                elif message.startswith("Processing file -"):
                    self.canvas.itemconfig(self.processing_label, text=message)
                else:
                    if success:
                        processed_files += 1
                    # Display all messages in the text area
                    self.message_area.config(state="normal")
                    self.message_area.insert("end", f"{message}\n")
                    self.message_area.config(state="disabled")
                    self.message_area.yview("end")  # Auto-scroll to the bottom

                    # Update progress bar
                    if total_files > 0:
                        self.progress['value'] = (processed_files / total_files) * 100
                        if processed_files == total_files:
                            self.processing_label = self.canvas.create_text(
                                600.0, 610.0, anchor="nw", text="Compression Successfully Done. Thank You.",
                                fill="#FFFFFF", font=("Terminal", 13 * -1)
                            )
                    self.root.update_idletasks()
            except Exception as e:
                logging.error(f"Error updating GUI: {str(e)}")
                break

if __name__ == "__main__":
    root = Tk()
    app = ImageCompressorApp(root)
    root.mainloop()