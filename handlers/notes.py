"""
Personal Notes
Users can save private notes inside the bot.
/note <text>     — save a note
/notes           — view all notes
/clearnotes      — delete all notes
"""
import json
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
import aiosqlite
from database.db import DB_PATH

router = Router()


async def get_notes(tg_id: int) -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT notes FROM users WHERE tg_id=?", (tg_id,)) as cur:
            row = await cur.fetchone()
        if not row or not row["notes"]:
            return []
        try:
            return json.loads(row["notes"])
        except Exception:
            return []


async def save_notes(tg_id: int, notes: list):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET notes=? WHERE tg_id=?", (json.dumps(notes, ensure_ascii=False), tg_id))
        await db.commit()


@router.message(Command("note"))
async def save_note(message: Message):
    text = message.text.partition(" ")[2].strip()
    if not text:
        await message.answer("Usage: /note <your note text>\n\nExample: /note Remember to study chapter 3")
        return
    notes = await get_notes(message.from_user.id)
    from datetime import datetime
    notes.append({"text": text, "date": datetime.now().strftime("%d %b %H:%M")})
    if len(notes) > 50:
        notes = notes[-50:]  # keep last 50
    await save_notes(message.from_user.id, notes)
    await message.answer(f"📝 <b>Note saved!</b>\n\n<i>{text[:200]}</i>\n\nYou have <b>{len(notes)}</b> note(s). Use /notes to view all.")


@router.message(Command("notes"))
async def view_notes(message: Message):
    notes = await get_notes(message.from_user.id)
    if not notes:
        await message.answer("📭 No notes yet.\n\nSave one with: /note <text>")
        return
    text = f"📝 <b>Your Notes</b>  ({len(notes)} total)\n\n"
    for i, n in enumerate(reversed(notes[-20:]), 1):
        text += f"<b>{i}.</b> {n['text'][:150]}\n<i>🕐 {n.get('date', '—')}</i>\n\n"
    if len(notes) > 20:
        text += f"<i>Showing last 20 of {len(notes)} notes.</i>"
    await message.answer(text)


@router.message(Command("clearnotes"))
async def clear_notes(message: Message):
    await save_notes(message.from_user.id, [])
    await message.answer("🗑 <b>All notes cleared.</b>")
