"""
CustomTkinter UI — modern dark dashboard for AI Social Media Automation.
"""

from __future__ import annotations

import json
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import Any, Callable

import customtkinter as ctk

from config import (
    COLORS,
    INDUSTRIES,
    LANGUAGES,
    PLATFORMS,
    TONES,
    config,
    save_env,
)
from database import db
from generator import GenerationRequest, clone_payload, generator
from image_generator import image_generator
from scheduler import post_scheduler
from social_api import publisher
from utils import (
    char_count,
    export_json,
    export_markdown,
    export_txt,
    get_logger,
    payload_to_markdown,
    quality_report,
    safe_json_dumps,
    word_count,
)

from PIL import Image
from pathlib import Path


logger = get_logger("ui")

# Layout constants
SIDEBAR_WIDTH = 220
APP_MIN_WIDTH = 1180
APP_MIN_HEIGHT = 760


class StatusBar(ctk.CTkFrame):
    """Bottom status bar with message + optional progress."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        super().__init__(master, height=36, fg_color=COLORS["sidebar"], **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.label = ctk.CTkLabel(
            self,
            text="Ready",
            text_color=COLORS["text_muted"],
            anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.label.grid(row=0, column=0, sticky="ew", padx=16, pady=6)
        self.progress = ctk.CTkProgressBar(
            self, width=140, height=8, progress_color=COLORS["accent"]
        )
        self.progress.grid(row=0, column=1, padx=16, pady=6)
        self.progress.set(0)
        self.progress.grid_remove()

    def set_status(self, text: str) -> None:
        self.label.configure(text=text)

    def start_progress(self) -> None:
        self.progress.grid()
        self.progress.configure(mode="indeterminate")
        self.progress.start()

    def stop_progress(self) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(0)
        self.progress.grid_remove()


class SidebarButton(ctk.CTkButton):
    """Navigation button with active-state styling."""

    def __init__(self, master: Any, text: str, command: Callable[[], None], **kwargs: Any) -> None:
        super().__init__(
            master,
            text=text,
            command=command,
            anchor="w",
            height=42,
            corner_radius=10,
            fg_color="transparent",
            hover_color=COLORS["card_hover"],
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=14, weight="normal"),
            **kwargs,
        )
        self._active = False

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            self.configure(fg_color=COLORS["card"], text_color=COLORS["accent"])
        else:
            self.configure(fg_color="transparent", text_color=COLORS["text"])


class Card(ctk.CTkFrame):
    """Rounded content card."""

    def __init__(self, master: Any, **kwargs: Any) -> None:
        kwargs.setdefault("fg_color", COLORS["card"])
        kwargs.setdefault("corner_radius", 14)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", COLORS["border"])
        super().__init__(master, **kwargs)


class SocialAppUI(ctk.CTk):
    """Root application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title("AI Social Media Automation")
        self.minsize(APP_MIN_WIDTH, APP_MIN_HEIGHT)
        self.geometry("1280x840")
        self.configure(fg_color=COLORS["bg"])

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        # State
        self.current_payload: dict[str, Any] | None = None
        self.current_post_id: int | None = None
        self.current_quality: dict[str, Any] | None = None
        self._nav_buttons: dict[str, SidebarButton] = {}
        self._pages: dict[str, ctk.CTkFrame] = {}
        self._preview_platform = tk.StringVar(value="LinkedIn")
        self._platform_vars = {p: tk.BooleanVar(value=True) for p in PLATFORMS}
        self._emoji_var = tk.BooleanVar(value=config.emoji_enabled)
        self._tone_mode_var = tk.StringVar(value=config.tone_mode or "Professional")
        self._auto_save_var = tk.BooleanVar(value=config.auto_save)
        self._auto_image_var = tk.BooleanVar(value=config.auto_generate_image)
        self.current_image_path: str | None = None
        self._preview_image_ref: ctk.CTkImage | None = None

        self._build_layout()
        self.show_page("dashboard")
        self.after(200, self._refresh_dashboard)

        # Scheduler callbacks into UI thread
        post_scheduler.on_status = lambda msg: self.after(0, lambda: self.status.set_status(msg))
        post_scheduler.start()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ layout
    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(
            self, width=SIDEBAR_WIDTH, corner_radius=0, fg_color=COLORS["sidebar"]
        )
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)

        brand = ctk.CTkLabel(
            self.sidebar,
            text="AI Social",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLORS["text"],
        )
        brand.grid(row=0, column=0, padx=20, pady=(28, 4), sticky="w")
        subtitle = ctk.CTkLabel(
            self.sidebar,
            text="Automation Studio",
            font=ctk.CTkFont(size=12),
            text_color=COLORS["text_muted"],
        )
        subtitle.grid(row=1, column=0, padx=20, pady=(0, 24), sticky="w")

        nav_items = [
            ("dashboard", "🏠  Dashboard"),
            ("generate", "✍  Generate Post"),
            ("scheduler", "📅  Scheduler"),
            ("history", "📂  History"),
            ("settings", "⚙  Settings"),
        ]
        for idx, (key, label) in enumerate(nav_items, start=2):
            btn = SidebarButton(self.sidebar, text=label, command=lambda k=key: self.show_page(k))
            btn.grid(row=idx, column=0, padx=12, pady=4, sticky="ew")
            self._nav_buttons[key] = btn

        self.content = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.status = StatusBar(self)
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew")

        self._pages["dashboard"] = self._build_dashboard(self.content)
        self._pages["generate"] = self._build_generate(self.content)
        self._pages["scheduler"] = self._build_scheduler(self.content)
        self._pages["history"] = self._build_history(self.content)
        self._pages["settings"] = self._build_settings(self.content)

        for page in self._pages.values():
            page.grid(row=0, column=0, sticky="nsew")
            page.grid_remove()

    def show_page(self, key: str) -> None:
        for name, page in self._pages.items():
            if name == key:
                page.grid()
            else:
                page.grid_remove()
        for name, btn in self._nav_buttons.items():
            btn.set_active(name == key)
        if key == "dashboard":
            self._refresh_dashboard()
        elif key == "history":
            self._refresh_history()
        elif key == "scheduler":
            self._refresh_schedules()
        self.status.set_status(f"{key.title()} ready")

    # -------------------------------------------------------------- dashboard
    def _build_dashboard(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure((0, 1, 2), weight=1)
        page.grid_rowconfigure(2, weight=1)

        header = ctk.CTkLabel(
            page,
            text="Dashboard",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLORS["text"],
            anchor="w",
        )
        header.grid(row=0, column=0, columnspan=3, padx=28, pady=(28, 8), sticky="w")
        hint = ctk.CTkLabel(
            page,
            text="Generate human-sounding posts, schedule them, and keep a searchable history.",
            text_color=COLORS["text_muted"],
            anchor="w",
        )
        hint.grid(row=1, column=0, columnspan=3, padx=28, pady=(0, 16), sticky="w")

        self.stat_labels: dict[str, ctk.CTkLabel] = {}
        cards = [
            ("posts", "Saved Posts"),
            ("pending_schedules", "Pending Schedules"),
            ("published_schedules", "Published"),
        ]
        for i, (key, title) in enumerate(cards):
            card = Card(page)
            card.grid(row=2, column=i, padx=16 if i else 28, pady=8, sticky="nsew")
            ctk.CTkLabel(
                card, text=title, text_color=COLORS["text_muted"], font=ctk.CTkFont(size=13)
            ).pack(anchor="w", padx=18, pady=(18, 4))
            value = ctk.CTkLabel(
                card, text="0", font=ctk.CTkFont(size=36, weight="bold"), text_color=COLORS["text"]
            )
            value.pack(anchor="w", padx=18, pady=(0, 18))
            self.stat_labels[key] = value

        health_card = Card(page)
        health_card.grid(row=3, column=0, columnspan=3, padx=28, pady=16, sticky="ew")
        ctk.CTkLabel(
            health_card,
            text="API & Token Status",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLORS["text"],
        ).pack(anchor="w", padx=18, pady=(16, 8))
        self.health_label = ctk.CTkLabel(
            health_card, text="", text_color=COLORS["text_muted"], justify="left", anchor="w"
        )
        self.health_label.pack(anchor="w", padx=18, pady=(0, 16))

        actions = ctk.CTkFrame(page, fg_color="transparent")
        actions.grid(row=4, column=0, columnspan=3, padx=28, pady=(8, 28), sticky="w")
        ctk.CTkButton(
            actions,
            text="Generate a Post",
            command=lambda: self.show_page("generate"),
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            corner_radius=10,
            height=40,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            actions,
            text="Open History",
            command=lambda: self.show_page("history"),
            fg_color=COLORS["card"],
            hover_color=COLORS["card_hover"],
            border_width=1,
            border_color=COLORS["border"],
            corner_radius=10,
            height=40,
        ).pack(side="left")
        return page

    def _refresh_dashboard(self) -> None:
        stats = db.stats()
        for key, label in self.stat_labels.items():
            label.configure(text=str(stats.get(key, 0)))
        health = publisher.health_check()
        lines = [f"{name}: {'Ready' if ok else 'Not set'}" for name, ok in health.items()]
        self.health_label.configure(text="  ·  ".join(lines))

    # --------------------------------------------------------------- generate
    def _build_generate(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=2)
        page.grid_columnconfigure(1, weight=3)
        page.grid_rowconfigure(0, weight=1)

        left = Card(page)
        left.grid(row=0, column=0, padx=(28, 10), pady=28, sticky="nsew")
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            left, text="Generate Post", font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, padx=18, pady=(18, 10), sticky="w")

        ctk.CTkLabel(left, text="Topic", text_color=COLORS["text_muted"]).grid(
            row=1, column=0, padx=18, sticky="w"
        )
        self.topic_box = ctk.CTkTextbox(
            left, height=90, fg_color=COLORS["input"], border_color=COLORS["border"], border_width=1
        )
        self.topic_box.grid(row=2, column=0, padx=18, pady=(4, 12), sticky="ew")

        form = ctk.CTkFrame(left, fg_color="transparent")
        form.grid(row=3, column=0, padx=18, sticky="ew")
        form.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(form, text="Industry", text_color=COLORS["text_muted"]).grid(
            row=0, column=0, sticky="w"
        )
        self.industry_menu = ctk.CTkOptionMenu(form, values=INDUSTRIES, height=34)
        self.industry_menu.set("Technology")
        self.industry_menu.grid(row=1, column=0, padx=(0, 8), pady=(2, 10), sticky="ew")

        ctk.CTkLabel(form, text="Tone", text_color=COLORS["text_muted"]).grid(
            row=0, column=1, sticky="w"
        )
        self.tone_menu = ctk.CTkOptionMenu(form, values=TONES, height=34)
        self.tone_menu.set("Professional")
        self.tone_menu.grid(row=1, column=1, pady=(2, 10), sticky="ew")

        ctk.CTkLabel(form, text="Language", text_color=COLORS["text_muted"]).grid(
            row=2, column=0, sticky="w"
        )
        self.language_menu = ctk.CTkOptionMenu(form, values=LANGUAGES, height=34)
        self.language_menu.set("English")
        self.language_menu.grid(row=3, column=0, padx=(0, 8), pady=(2, 10), sticky="ew")

        ctk.CTkLabel(form, text="Tone Mode", text_color=COLORS["text_muted"]).grid(
            row=2, column=1, sticky="w"
        )
        self.tone_mode_menu = ctk.CTkOptionMenu(
            form, values=["Professional", "Casual"], variable=self._tone_mode_var, height=34
        )
        self.tone_mode_menu.grid(row=3, column=1, pady=(2, 10), sticky="ew")

        ctk.CTkLabel(left, text="Platforms", text_color=COLORS["text_muted"]).grid(
            row=4, column=0, padx=18, sticky="w"
        )
        plat_row = ctk.CTkFrame(left, fg_color="transparent")
        plat_row.grid(row=5, column=0, padx=18, pady=(4, 8), sticky="w")
        for i, p in enumerate(PLATFORMS):
            ctk.CTkCheckBox(plat_row, text=p, variable=self._platform_vars[p]).grid(
                row=0, column=i, padx=(0, 12)
            )

        ctk.CTkLabel(left, text="Word Count Target", text_color=COLORS["text_muted"]).grid(
            row=6, column=0, padx=18, sticky="w"
        )
        self.word_slider = ctk.CTkSlider(left, from_=80, to=300, number_of_steps=44)
        self.word_slider.set(config.default_word_count)
        self.word_slider.grid(row=7, column=0, padx=18, pady=(4, 2), sticky="ew")
        self.word_value_label = ctk.CTkLabel(left, text=f"{config.default_word_count} words")
        self.word_value_label.grid(row=8, column=0, padx=18, sticky="w")
        self.word_slider.configure(
            command=lambda v: self.word_value_label.configure(text=f"{int(float(v))} words")
        )

        toggles = ctk.CTkFrame(left, fg_color="transparent")
        toggles.grid(row=9, column=0, padx=18, pady=10, sticky="w")
        ctk.CTkCheckBox(toggles, text="Emojis", variable=self._emoji_var).pack(
            side="left", padx=(0, 12)
        )
        ctk.CTkCheckBox(toggles, text="Auto Save", variable=self._auto_save_var).pack(
            side="left", padx=(0, 12)
        )
        ctk.CTkCheckBox(
            toggles, text="Auto Image", variable=self._auto_image_var
        ).pack(side="left")

        actions = ctk.CTkFrame(left, fg_color="transparent")
        actions.grid(row=10, column=0, padx=18, pady=(8, 8), sticky="ew")
        ctk.CTkButton(
            actions,
            text="Generate",
            command=self._on_generate,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            height=40,
            corner_radius=10,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Regenerate",
            command=self._on_generate,
            fg_color=COLORS["card_hover"],
            height=40,
            corner_radius=10,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="AI Rewrite",
            command=self._on_rewrite,
            fg_color=COLORS["card_hover"],
            height=40,
            corner_radius=10,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            actions,
            text="Generate Image",
            command=self._on_generate_image,
            fg_color=COLORS["success"],
            hover_color="#34b87a",
            text_color="#0f1115",
            height=40,
            corner_radius=10,
        ).pack(side="left")

        # Preview column
        right = Card(page)
        right.grid(row=0, column=1, padx=(10, 28), pady=28, sticky="nsew")
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(2, weight=1)

        top = ctk.CTkFrame(right, fg_color="transparent")
        top.grid(row=0, column=0, padx=18, pady=(18, 8), sticky="ew")
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="Preview", font=ctk.CTkFont(size=22, weight="bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.preview_menu = ctk.CTkOptionMenu(
            top,
            values=PLATFORMS + ["Image Prompt", "Generated Image", "JSON", "Summary"],
            variable=self._preview_platform,
            command=lambda _: self._render_preview(),
            width=170,
        )
        self.preview_menu.grid(row=0, column=1, sticky="e")

        self.counter_label = ctk.CTkLabel(
            right, text="0 chars  ·  0 words", text_color=COLORS["text_muted"]
        )
        self.counter_label.grid(row=1, column=0, padx=18, sticky="w")

        self.preview_box = ctk.CTkTextbox(
            right, fg_color=COLORS["input"], border_color=COLORS["border"], border_width=1
        )
        self.preview_box.grid(row=2, column=0, padx=18, pady=8, sticky="nsew")

        self.image_preview_label = ctk.CTkLabel(
            right,
            text="No image yet — enable Auto Image or click Generate Image",
            text_color=COLORS["text_muted"],
            fg_color=COLORS["input"],
            corner_radius=10,
            height=220,
        )
        self.image_preview_label.grid(row=2, column=0, padx=18, pady=8, sticky="nsew")
        self.image_preview_label.grid_remove()

        self.quality_label = ctk.CTkLabel(
            right, text="Quality: —", text_color=COLORS["text_muted"], anchor="w"
        )
        self.quality_label.grid(row=3, column=0, padx=18, sticky="w")

        toolbar = ctk.CTkFrame(right, fg_color="transparent")
        toolbar.grid(row=4, column=0, padx=18, pady=(8, 18), sticky="ew")
        buttons = [
            ("Copy", self._copy_preview),
            ("Copy All", self._copy_all),
            ("Save", self._save_post),
            ("JSON", self._export_json),
            ("Markdown", self._export_md),
            ("TXT", self._export_txt),
            ("Open Image", self._open_image),
            ("Schedule", self._quick_schedule),
        ]
        for text, cmd in buttons:
            ctk.CTkButton(
                toolbar,
                text=text,
                command=cmd,
                width=88,
                height=34,
                corner_radius=8,
                fg_color=COLORS["card_hover"],
                hover_color=COLORS["border"],
            ).pack(side="left", padx=(0, 6))
        return page

    def _selected_platforms(self) -> list[str]:
        return [p for p, var in self._platform_vars.items() if var.get()]

    def _build_request(self) -> GenerationRequest:
        topic = self.topic_box.get("1.0", "end").strip()
        platforms = self._selected_platforms()
        if not platforms:
            raise ValueError("Select at least one platform.")
        return GenerationRequest(
            topic=topic,
            industry=self.industry_menu.get(),
            tone=self.tone_menu.get(),
            language=self.language_menu.get(),
            platforms=platforms,
            word_count=int(float(self.word_slider.get())),
            emoji_enabled=bool(self._emoji_var.get()),
            tone_mode=self._tone_mode_var.get(),
        )

    def _run_async(self, work: Callable[[], None], busy_msg: str = "Working…") -> None:
        self.status.set_status(busy_msg)
        self.status.start_progress()

        def runner() -> None:
            try:
                work()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Background task failed")
                self.after(0, lambda: messagebox.showerror("Error", str(exc)))
                self.after(0, lambda: self.status.set_status(f"Error: {exc}"))
            finally:
                self.after(0, self.status.stop_progress)

        threading.Thread(target=runner, daemon=True).start()

    def _on_generate(self) -> None:
        try:
            request = self._build_request()
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("Missing input", str(exc))
            return
        if not request.topic:
            messagebox.showwarning("Missing topic", "Please enter a topic.")
            return

        auto_image = bool(self._auto_image_var.get())

        def work() -> None:
            result = generator.generate(request)
            image_path: str | None = None
            image_provider = ""
            if auto_image:
                self.after(
                    0, lambda: self.status.set_status("Generating post image…")
                )
                img = image_generator.generate(
                    result.payload.get("image_prompt", ""),
                    topic=result.payload.get("topic", request.topic),
                )
                image_path = str(img.path)
                image_provider = img.provider
                result.payload["image_path"] = image_path
                result.payload["image_provider"] = image_provider

            def apply() -> None:
                self.current_payload = result.payload
                self.current_quality = result.quality
                self.current_post_id = None
                self.current_image_path = image_path
                self._render_preview()
                if image_path:
                    self._show_generated_image(image_path)
                    self._preview_platform.set("Generated Image")
                    self._render_preview()
                msg = f"Generated via {result.provider}"
                if image_provider:
                    msg += f" · image via {image_provider}"
                self.status.set_status(msg)
                if self._auto_save_var.get():
                    self._save_post(silent=True)

            self.after(0, apply)

        self._run_async(work, "Generating content…")

    def _on_generate_image(self) -> None:
        if not self.current_payload:
            messagebox.showinfo(
                "Generate Image",
                "Generate a post first (needs an image prompt).",
            )
            return
        prompt = str(self.current_payload.get("image_prompt", "")).strip()
        topic = str(self.current_payload.get("topic", "")).strip()

        def work() -> None:
            img = image_generator.generate(prompt, topic=topic)

            def apply() -> None:
                self.current_image_path = str(img.path)
                if self.current_payload is not None:
                    self.current_payload["image_path"] = str(img.path)
                    self.current_payload["image_provider"] = img.provider
                self._show_generated_image(str(img.path))
                self._preview_platform.set("Generated Image")
                self._render_preview()
                self.status.set_status(f"Image ready via {img.provider}")
                if self._auto_save_var.get():
                    self._save_post(silent=True)

            self.after(0, apply)

        self._run_async(work, "Generating image…")

    def _show_generated_image(self, path: str) -> None:
        try:
            pil = Image.open(path)
            pil = pil.convert("RGB")
            # Fit preview area
            max_w, max_h = 420, 420
            pil.thumbnail((max_w, max_h))
            self._preview_image_ref = ctk.CTkImage(
                light_image=pil, dark_image=pil, size=pil.size
            )
            self.image_preview_label.configure(
                image=self._preview_image_ref, text=""
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not display image: %s", exc)
            self.image_preview_label.configure(
                image=None, text=f"Image saved:\n{path}"
            )

    def _open_image(self) -> None:
        path = self.current_image_path
        if not path and self.current_payload:
            path = self.current_payload.get("image_path")
        if not path or not Path(str(path)).exists():
            messagebox.showinfo("Open Image", "No generated image yet.")
            return
        try:
            import os
            import subprocess
            import sys

            p = str(path)
            if sys.platform == "darwin":
                subprocess.run(["open", p], check=False)
            elif os.name == "nt":
                os.startfile(p)  # type: ignore[attr-defined]
            else:
                subprocess.run(["xdg-open", p], check=False)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Open Image", str(exc))

    def _on_rewrite(self) -> None:
        if not self.current_payload:
            messagebox.showinfo("Nothing to rewrite", "Generate a post first.")
            return

        def work() -> None:
            result = generator.rewrite(
                self.current_payload or {},
                instruction="Rewrite to sound warmer and more human. Keep structure.",
                platforms=self._selected_platforms(),
            )

            def apply() -> None:
                self.current_payload = result.payload
                self.current_quality = result.quality
                self._render_preview()
                self.status.set_status(f"Rewritten via {result.provider}")
                if self._auto_save_var.get():
                    self._save_post(silent=True)

            self.after(0, apply)

        self._run_async(work, "Rewriting…")

    def _preview_text(self) -> str:
        payload = self.current_payload
        if not payload:
            return "Generate a post to preview content here."
        view = self._preview_platform.get()
        if view == "LinkedIn":
            b = payload.get("linkedin", {})
            return f"{b.get('title', '')}\n\n{b.get('content', '')}\n\n{' '.join(b.get('hashtags', []))}".strip()
        if view == "X":
            b = payload.get("x", {})
            return f"{b.get('content', '')}\n{' '.join(b.get('hashtags', []))}".strip()
        if view == "Facebook":
            b = payload.get("facebook", {})
            return f"{b.get('content', '')}\n\n{' '.join(b.get('hashtags', []))}".strip()
        if view == "Instagram":
            b = payload.get("instagram", {})
            return f"{b.get('caption', '')}\n\n{' '.join(b.get('hashtags', []))}".strip()
        if view == "Image Prompt":
            return str(payload.get("image_prompt", ""))
        if view == "JSON":
            return safe_json_dumps(payload)
        # Summary
        return (
            f"Title: {payload.get('title', '')}\n"
            f"Topic: {payload.get('topic', '')}\n"
            f"Summary: {payload.get('summary', '')}\n"
            f"CTA: {payload.get('cta', '')}\n"
            f"Keywords: {', '.join(payload.get('keywords', []))}"
        )

    def _render_preview(self) -> None:
        view = self._preview_platform.get()
        show_image = view == "Generated Image"
        if show_image:
            self.preview_box.grid_remove()
            self.image_preview_label.grid()
            if self.current_image_path and Path(self.current_image_path).exists():
                self._show_generated_image(self.current_image_path)
                self.counter_label.configure(text=f"Image: {Path(self.current_image_path).name}")
            else:
                self.image_preview_label.configure(
                    image=None,
                    text="No image yet — enable Auto Image or click Generate Image",
                )
                self.counter_label.configure(text="No image")
        else:
            self.image_preview_label.grid_remove()
            self.preview_box.grid()
            text = self._preview_text()
            self.preview_box.delete("1.0", "end")
            self.preview_box.insert("1.0", text)
            self.counter_label.configure(
                text=f"{char_count(text)} chars  ·  {word_count(text)} words"
            )

        if self.current_quality:
            q = self.current_quality
        elif self.current_payload:
            q = quality_report(self.current_payload)
            self.current_quality = q
        else:
            q = None
        if q:
            x_flag = "OK" if q.get("x_ok") else "OVER LIMIT"
            self.quality_label.configure(
                text=(
                    f"Quality · Readability {q.get('readability')} ({q.get('readability_label')})  ·  "
                    f"Uniqueness {q.get('uniqueness')}  ·  X {q.get('x_chars')}/280 [{x_flag}]"
                )
            )

    def _copy_preview(self) -> None:
        text = self.preview_box.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set_status("Copied preview to clipboard")

    def _copy_all(self) -> None:
        if not self.current_payload:
            return
        text = payload_to_markdown(self.current_payload)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.set_status("Copied all platforms to clipboard")

    def _save_post(self, silent: bool = False) -> None:
        if not self.current_payload:
            if not silent:
                messagebox.showinfo("Nothing to save", "Generate a post first.")
            return
        post_id = db.save_post(
            self.current_payload,
            industry=self.industry_menu.get(),
            tone=self.tone_menu.get(),
            language=self.language_menu.get(),
            platforms=self._selected_platforms(),
            post_id=self.current_post_id,
        )
        self.current_post_id = post_id
        self.status.set_status(f"Saved post #{post_id}")
        if not silent:
            messagebox.showinfo("Saved", f"Post #{post_id} saved to history.")

    def _export_json(self) -> None:
        if not self.current_payload:
            return
        path = export_json(self.current_payload)
        self.status.set_status(f"Exported JSON → {path.name}")
        messagebox.showinfo("Exported", f"Saved:\n{path}")

    def _export_md(self) -> None:
        if not self.current_payload:
            return
        path = export_markdown(self.current_payload)
        self.status.set_status(f"Exported Markdown → {path.name}")
        messagebox.showinfo("Exported", f"Saved:\n{path}")

    def _export_txt(self) -> None:
        if not self.current_payload:
            return
        path = export_txt(self.current_payload)
        self.status.set_status(f"Exported TXT → {path.name}")
        messagebox.showinfo("Exported", f"Saved:\n{path}")

    def _quick_schedule(self) -> None:
        if not self.current_payload:
            messagebox.showinfo("Schedule", "Generate and save a post first.")
            return
        if not self.current_post_id:
            self._save_post(silent=True)
        self.show_page("scheduler")
        if self.current_post_id:
            self.schedule_post_id.set(str(self.current_post_id))

    # -------------------------------------------------------------- scheduler
    def _build_scheduler(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            page, text="Scheduler", font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, padx=28, pady=(28, 8), sticky="w")

        form = Card(page)
        form.grid(row=1, column=0, padx=28, pady=8, sticky="ew")
        for i in range(6):
            form.grid_columnconfigure(i, weight=1)

        ctk.CTkLabel(form, text="Post ID").grid(row=0, column=0, padx=12, pady=(14, 2), sticky="w")
        self.schedule_post_id = ctk.CTkEntry(form, placeholder_text="e.g. 1")
        self.schedule_post_id.grid(row=1, column=0, padx=12, pady=(0, 14), sticky="ew")

        ctk.CTkLabel(form, text="Platform").grid(row=0, column=1, padx=12, pady=(14, 2), sticky="w")
        self.schedule_platform = ctk.CTkOptionMenu(form, values=PLATFORMS)
        self.schedule_platform.set("LinkedIn")
        self.schedule_platform.grid(row=1, column=1, padx=12, pady=(0, 14), sticky="ew")

        ctk.CTkLabel(form, text="Date (YYYY-MM-DD)").grid(
            row=0, column=2, padx=12, pady=(14, 2), sticky="w"
        )
        self.schedule_date = ctk.CTkEntry(form, placeholder_text="2026-07-16")
        self.schedule_date.insert(0, datetime.now().strftime("%Y-%m-%d"))
        self.schedule_date.grid(row=1, column=2, padx=12, pady=(0, 14), sticky="ew")

        ctk.CTkLabel(form, text="Time (HH:MM)").grid(
            row=0, column=3, padx=12, pady=(14, 2), sticky="w"
        )
        self.schedule_time = ctk.CTkEntry(form, placeholder_text="09:30")
        self.schedule_time.insert(0, "09:30")
        self.schedule_time.grid(row=1, column=3, padx=12, pady=(0, 14), sticky="ew")

        ctk.CTkLabel(form, text="Notes").grid(row=0, column=4, padx=12, pady=(14, 2), sticky="w")
        self.schedule_notes = ctk.CTkEntry(form, placeholder_text="Optional")
        self.schedule_notes.grid(row=1, column=4, padx=12, pady=(0, 14), sticky="ew")

        ctk.CTkButton(
            form,
            text="Schedule",
            command=self._add_schedule,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            height=36,
            corner_radius=10,
        ).grid(row=1, column=5, padx=12, pady=(0, 14), sticky="ew")

        list_card = Card(page)
        list_card.grid(row=2, column=0, padx=28, pady=(8, 28), sticky="nsew")
        list_card.grid_columnconfigure(0, weight=1)
        list_card.grid_rowconfigure(1, weight=1)
        header = ctk.CTkFrame(list_card, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=14, pady=12)
        ctk.CTkLabel(header, text="Upcoming & Recent", font=ctk.CTkFont(size=16, weight="bold")).pack(
            side="left"
        )
        ctk.CTkButton(
            header, text="Refresh", width=90, command=self._refresh_schedules, height=30
        ).pack(side="right")
        self.schedule_list = ctk.CTkTextbox(list_card, fg_color=COLORS["input"])
        self.schedule_list.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")
        return page

    def _add_schedule(self) -> None:
        try:
            post_id = int(self.schedule_post_id.get().strip())
            date_s = self.schedule_date.get().strip()
            time_s = self.schedule_time.get().strip()
            when = datetime.strptime(f"{date_s} {time_s}", "%Y-%m-%d %H:%M")
            sid = post_scheduler.schedule_post(
                post_id,
                self.schedule_platform.get(),
                when,
                notes=self.schedule_notes.get().strip(),
            )
            messagebox.showinfo("Scheduled", f"Schedule #{sid} created.")
            self._refresh_schedules()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Schedule error", str(exc))

    def _refresh_schedules(self) -> None:
        rows = db.list_schedules()
        self.schedule_list.delete("1.0", "end")
        if not rows:
            self.schedule_list.insert("1.0", "No schedules yet.")
            return
        lines = []
        for r in rows:
            lines.append(
                f"#{r.id}  post={r.post_id}  {r.platform:<10}  {r.scheduled_at}  [{r.status}]  {r.notes}"
            )
        self.schedule_list.insert("1.0", "\n".join(lines))

    # ---------------------------------------------------------------- history
    def _build_history(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            page, text="History", font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, padx=28, pady=(28, 8), sticky="w")

        search_row = ctk.CTkFrame(page, fg_color="transparent")
        search_row.grid(row=1, column=0, padx=28, sticky="ew")
        search_row.grid_columnconfigure(0, weight=1)
        self.history_search = ctk.CTkEntry(search_row, placeholder_text="Search posts…")
        self.history_search.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ctk.CTkButton(search_row, text="Search", width=90, command=self._refresh_history).grid(
            row=0, column=1, padx=(0, 6)
        )
        ctk.CTkButton(search_row, text="Reuse", width=90, command=self._reuse_selected).grid(
            row=0, column=2, padx=(0, 6)
        )
        ctk.CTkButton(search_row, text="Edit", width=90, command=self._edit_selected).grid(
            row=0, column=3, padx=(0, 6)
        )
        ctk.CTkButton(
            search_row,
            text="Delete",
            width=90,
            fg_color=COLORS["danger"],
            hover_color="#d45555",
            command=self._delete_selected,
        ).grid(row=0, column=4)

        body = Card(page)
        body.grid(row=2, column=0, padx=28, pady=(12, 28), sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self.history_listbox = tk.Listbox(
            body,
            bg=COLORS["input"],
            fg=COLORS["text"],
            selectbackground=COLORS["accent"],
            highlightthickness=0,
            borderwidth=0,
            font=("Menlo", 12),
        )
        self.history_listbox.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        self.history_listbox.bind("<<ListboxSelect>>", lambda _e: self._show_history_detail())

        self.history_detail = ctk.CTkTextbox(body, fg_color=COLORS["input"])
        self.history_detail.grid(row=0, column=1, sticky="nsew", padx=(0, 12), pady=12)
        self._history_ids: list[int] = []
        return page

    def _refresh_history(self) -> None:
        query = self.history_search.get().strip() if hasattr(self, "history_search") else ""
        posts = db.list_posts(query=query)
        self.history_listbox.delete(0, "end")
        self._history_ids = []
        for post in posts:
            self._history_ids.append(post.id)
            label = f"#{post.id}  {post.created_at}  {post.title or post.topic}"
            self.history_listbox.insert("end", label)
        self.history_detail.delete("1.0", "end")
        if not posts:
            self.history_detail.insert("1.0", "No posts found.")

    def _selected_history_id(self) -> int | None:
        sel = self.history_listbox.curselection()
        if not sel:
            return None
        idx = int(sel[0])
        if idx < 0 or idx >= len(self._history_ids):
            return None
        return self._history_ids[idx]

    def _show_history_detail(self) -> None:
        post_id = self._selected_history_id()
        if post_id is None:
            return
        post = db.get_post(post_id)
        if not post:
            return
        self.history_detail.delete("1.0", "end")
        self.history_detail.insert("1.0", payload_to_markdown(post.payload))

    def _reuse_selected(self) -> None:
        post_id = self._selected_history_id()
        if post_id is None:
            messagebox.showinfo("Reuse", "Select a post first.")
            return
        post = db.get_post(post_id)
        if not post:
            return
        self.current_payload = clone_payload(post.payload)
        self.current_post_id = None
        self.current_quality = quality_report(self.current_payload)
        self.current_image_path = (
            str(self.current_payload.get("image_path"))
            if self.current_payload.get("image_path")
            else None
        )
        self.topic_box.delete("1.0", "end")
        self.topic_box.insert("1.0", post.topic)
        if post.industry:
            self.industry_menu.set(post.industry)
        if post.tone:
            self.tone_menu.set(post.tone)
        if post.language:
            self.language_menu.set(post.language)
        self.show_page("generate")
        self._render_preview()
        self.status.set_status(f"Reused post #{post_id}")

    def _edit_selected(self) -> None:
        post_id = self._selected_history_id()
        if post_id is None:
            messagebox.showinfo("Edit", "Select a post first.")
            return
        post = db.get_post(post_id)
        if not post:
            return
        self.current_payload = clone_payload(post.payload)
        self.current_post_id = post.id
        self.current_quality = quality_report(self.current_payload)
        self.topic_box.delete("1.0", "end")
        self.topic_box.insert("1.0", post.topic)
        self.show_page("generate")
        self._render_preview()
        self.status.set_status(f"Editing post #{post_id} — Save to update")

    def _delete_selected(self) -> None:
        post_id = self._selected_history_id()
        if post_id is None:
            return
        if not messagebox.askyesno("Delete", f"Delete post #{post_id}?"):
            return
        db.delete_post(post_id)
        self._refresh_history()
        self.status.set_status(f"Deleted post #{post_id}")

    # --------------------------------------------------------------- settings
    def _build_settings(self, parent: ctk.CTkFrame) -> ctk.CTkFrame:
        page = ctk.CTkFrame(parent, fg_color="transparent")
        page.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            page, text="Settings", font=ctk.CTkFont(size=28, weight="bold")
        ).grid(row=0, column=0, padx=28, pady=(28, 8), sticky="w")

        card = Card(page)
        card.grid(row=1, column=0, padx=28, pady=(8, 28), sticky="nsew")
        card.grid_columnconfigure(1, weight=1)

        fields = [
            ("OPENAI_API_KEY", "OpenAI API Key", config.openai_api_key),
            ("NVIDIA_API_KEY", "NVIDIA API Key", config.nvidia_api_key),
            ("LINKEDIN_TOKEN", "LinkedIn Token", config.linkedin_token),
            ("FACEBOOK_TOKEN", "Facebook Token", config.facebook_token),
            ("INSTAGRAM_TOKEN", "Instagram Token", config.instagram_token),
            ("X_TOKEN", "X Token", config.x_token),
            ("OPENAI_MODEL", "OpenAI Model", config.openai_model),
            ("NVIDIA_MODEL", "NVIDIA Model", config.nvidia_model),
        ]
        self.settings_entries: dict[str, ctk.CTkEntry] = {}
        for i, (key, label, value) in enumerate(fields):
            ctk.CTkLabel(card, text=label, text_color=COLORS["text_muted"]).grid(
                row=i, column=0, padx=18, pady=10, sticky="w"
            )
            show = "*" if "KEY" in key or "TOKEN" in key else ""
            entry = ctk.CTkEntry(card, show=show, height=36)
            entry.insert(0, value or "")
            entry.grid(row=i, column=1, padx=18, pady=10, sticky="ew")
            self.settings_entries[key] = entry

        options = ctk.CTkFrame(card, fg_color="transparent")
        options.grid(row=len(fields), column=0, columnspan=2, padx=18, pady=8, sticky="w")
        self.dark_mode_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(options, text="Dark Mode", variable=self.dark_mode_var).pack(
            side="left", padx=(0, 16)
        )
        self.nvidia_fallback_var = tk.BooleanVar(value=config.use_nvidia_fallback)
        ctk.CTkCheckBox(
            options, text="NVIDIA Fallback", variable=self.nvidia_fallback_var
        ).pack(side="left")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=len(fields) + 1, column=0, columnspan=2, padx=18, pady=(8, 20), sticky="w")
        ctk.CTkButton(
            btn_row,
            text="Save to .env",
            command=self._save_settings,
            fg_color=COLORS["accent"],
            hover_color=COLORS["accent_hover"],
            height=40,
            corner_radius=10,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btn_row,
            text="Export Posts Folder…",
            command=self._open_posts_folder,
            height=40,
            corner_radius=10,
            fg_color=COLORS["card_hover"],
        ).pack(side="left")
        return page

    def _save_settings(self) -> None:
        values = {k: e.get().strip() for k, e in self.settings_entries.items()}
        values["DARK_MODE"] = "true" if self.dark_mode_var.get() else "false"
        values["USE_NVIDIA_FALLBACK"] = (
            "true" if self.nvidia_fallback_var.get() else "false"
        )
        values["EMOJI_ENABLED"] = "true" if self._emoji_var.get() else "false"
        values["AUTO_SAVE"] = "true" if self._auto_save_var.get() else "false"
        values["AUTO_GENERATE_IMAGE"] = (
            "true" if self._auto_image_var.get() else "false"
        )
        values["TONE_MODE"] = self._tone_mode_var.get()
        save_env(values)
        config.reload()
        ctk.set_appearance_mode("dark" if self.dark_mode_var.get() else "light")
        self.status.set_status("Settings saved to .env")
        messagebox.showinfo("Settings", "Saved successfully.")
        self._refresh_dashboard()

    def _open_posts_folder(self) -> None:
        path = filedialog.askdirectory(title="Posts are saved under the project posts/ folder")
        if path:
            self.status.set_status(f"Selected: {path}")

    def _on_close(self) -> None:
        try:
            post_scheduler.stop()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()


def run_app() -> None:
    """Launch the UI application."""
    app = SocialAppUI()
    app.mainloop()
