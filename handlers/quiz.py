"""
Quiz System — Full Rewrite
- Admin panel button → Quiz Management
- Full inline keyboard flow (no commands needed)
- Rewards: every 5 correct → 1 Free Pass, every 10 correct → 2 Free Passes
- "Next Quiz" button after each answer
- Score streak tracking
"""
import logging
import aiosqlite
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import DB_PATH
from database.users import add_free_pass
from config import settings
from keyboards.user import main_menu_kb, cancel_kb
from keyboards.admin import back_admin_kb

router = Router()
logger = logging.getLogger(__name__)


def is_admin(uid): return uid in settings.admin_id_list


# ─── DB ───────────────────────────────────────────────────────

async def get_random_quiz(user_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT q.* FROM quizzes q
               WHERE q.id NOT IN (SELECT quiz_id FROM quiz_answers WHERE user_id=?)
               ORDER BY RANDOM() LIMIT 1""",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            async with db.execute("SELECT * FROM quizzes ORDER BY RANDOM() LIMIT 1") as cur:
                row = await cur.fetchone()
        return dict(row) if row else None


async def get_quiz_by_id(quiz_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM quizzes WHERE id=?", (quiz_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None


async def save_answer(user_id: int, quiz_id: int, answer: str, correct: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO quiz_answers (user_id, quiz_id, answer, is_correct) VALUES (?,?,?,?)",
            (user_id, quiz_id, answer, int(correct))
        )
        await db.commit()


async def get_quiz_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT COUNT(*) as total, SUM(is_correct) as correct FROM quiz_answers WHERE user_id=?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
        total   = row["total"] or 0
        correct = int(row["correct"] or 0)
        return {"total": total, "correct": correct, "wrong": total - correct}


async def get_all_quizzes() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM quizzes ORDER BY id DESC") as cur:
            return [dict(r) for r in await cur.fetchall()]


async def db_add_quiz(question, a, b, c, d, correct, explanation=None) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO quizzes (question,option_a,option_b,option_c,option_d,correct,explanation) "
            "VALUES (?,?,?,?,?,?,?)",
            (question, a, b, c, d, correct.upper(), explanation)
        )
        await db.commit()
        return cur.lastrowid


async def db_delete_quiz(quiz_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM quizzes WHERE id=?", (quiz_id,))
        await db.execute("DELETE FROM quiz_answers WHERE quiz_id=?", (quiz_id,))
        await db.commit()


async def get_quiz_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) as c FROM quizzes") as cur:
            return (await cur.fetchone())["c"]


# ─── KEYBOARDS ────────────────────────────────────────────────

def quiz_options_kb(quiz_id: int, a: str, b: str, c: str, d: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🅐  {a[:38]}", callback_data=f"qans:{quiz_id}:A")],
        [InlineKeyboardButton(text=f"🅑  {b[:38]}", callback_data=f"qans:{quiz_id}:B")],
        [InlineKeyboardButton(text=f"🅒  {c[:38]}", callback_data=f"qans:{quiz_id}:C")],
        [InlineKeyboardButton(text=f"🅓  {d[:38]}", callback_data=f"qans:{quiz_id}:D")],
    ])


def after_quiz_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➡️ Next Quiz", callback_data="quiz:next"),
        InlineKeyboardButton(text="📊 My Score",  callback_data="quiz:score"),
    ]])


def admin_quiz_kb(quizzes: list) -> InlineKeyboardMarkup:
    builder_rows = []
    for q in quizzes[:15]:
        label = q["question"][:40] + ("…" if len(q["question"]) > 40 else "")
        builder_rows.append([
            InlineKeyboardButton(text=f"📝 {label}", callback_data=f"qview:{q['id']}"),
            InlineKeyboardButton(text="🗑",           callback_data=f"qdel:{q['id']}"),
        ])
    builder_rows.append([InlineKeyboardButton(text="➕ Add Quiz",  callback_data="qadd")])
    builder_rows.append([InlineKeyboardButton(text="◀️ Back",      callback_data="adm:main")])
    return InlineKeyboardMarkup(inline_keyboard=builder_rows)


# ─── USER: take quiz ──────────────────────────────────────────

@router.message(Command("quiz"))
@router.message(F.text == "🧠 Quiz")
async def send_quiz(message: Message):
    quiz = await get_random_quiz(message.from_user.id)
    if not quiz:
        await message.answer(
            "📭 <b>No quizzes available yet.</b>\n\nAsk the admin to add some questions!"
        )
        return
    stats = await get_quiz_stats(message.from_user.id)
    await message.answer(
        f"🧠 <b>Quiz</b>  —  Score: {stats['correct']}/{stats['total']}\n\n"
        f"<b>{quiz['question']}</b>",
        reply_markup=quiz_options_kb(quiz["id"], quiz["option_a"], quiz["option_b"],
                                     quiz["option_c"], quiz["option_d"])
    )


@router.callback_query(F.data == "quiz:next")
async def next_quiz(call: CallbackQuery):
    quiz = await get_random_quiz(call.from_user.id)
    if not quiz:
        await call.answer("No more quizzes!", show_alert=True)
        return
    stats = await get_quiz_stats(call.from_user.id)
    await call.message.edit_text(
        f"🧠 <b>Quiz</b>  —  Score: {stats['correct']}/{stats['total']}\n\n"
        f"<b>{quiz['question']}</b>",
        reply_markup=quiz_options_kb(quiz["id"], quiz["option_a"], quiz["option_b"],
                                     quiz["option_c"], quiz["option_d"])
    )
    await call.answer()


@router.callback_query(F.data == "quiz:score")
async def quiz_score(call: CallbackQuery):
    stats = await get_quiz_stats(call.from_user.id)
    total   = stats["total"]
    correct = stats["correct"]
    pct     = int(correct / total * 100) if total else 0
    await call.answer(
        f"📊 Your Score\n✅ {correct} correct\n❌ {stats['wrong']} wrong\n🎯 {pct}% accuracy",
        show_alert=True
    )


@router.callback_query(F.data.startswith("qans:"))
async def quiz_answer(call: CallbackQuery, bot: Bot):
    parts   = call.data.split(":")
    quiz_id = int(parts[1])
    answer  = parts[2].upper()

    quiz = await get_quiz_by_id(quiz_id)
    if not quiz:
        await call.answer("Quiz not found.", show_alert=True)
        return

    correct    = quiz["correct"].upper()
    is_correct = answer == correct
    await save_answer(call.from_user.id, quiz_id, answer, is_correct)
    stats = await get_quiz_stats(call.from_user.id)

    opts = {"A": quiz["option_a"], "B": quiz["option_b"],
            "C": quiz["option_c"], "D": quiz["option_d"]}
    explanation = f"\n\n💡 <i>{quiz['explanation']}</i>" if quiz.get("explanation") else ""

    # ── Reward logic ──────────────────────────────────────────
    reward_line = ""
    if is_correct:
        c = stats["correct"]
        if c > 0 and c % 10 == 0:
            await add_free_pass(call.from_user.id, 2)
            reward_line = f"\n\n🎉 <b>+2 Free Passes</b> for {c} correct answers! 🔥"
        elif c > 0 and c % 5 == 0:
            await add_free_pass(call.from_user.id, 1)
            reward_line = f"\n\n🎫 <b>+1 Free Pass</b> for {c} correct answers!"

    if is_correct:
        result_header = f"✅ <b>Correct!</b>  +1 point"
        answer_line   = f"✔️ <b>{correct}.</b> {opts[correct]}"
    else:
        result_header = f"❌ <b>Wrong!</b>"
        answer_line   = (
            f"✗ You chose: {answer}. {opts.get(answer, '?')}\n"
            f"✔️ Correct: <b>{correct}.</b> {opts[correct]}"
        )

    score_line = f"\n📊 Score: <b>{stats['correct']}</b> correct / <b>{stats['total']}</b> answered"

    await call.message.edit_text(
        f"{result_header}\n\n"
        f"<b>{quiz['question']}</b>\n\n"
        f"{answer_line}"
        f"{explanation}"
        f"{reward_line}"
        f"{score_line}",
        reply_markup=after_quiz_kb()
    )
    await call.answer("✅ Correct!" if is_correct else "❌ Wrong!")


# ─── ADMIN PANEL ──────────────────────────────────────────────

@router.callback_query(F.data == "adm:quiz")
async def adm_quiz_panel(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    quizzes = await get_all_quizzes()
    count   = len(quizzes)
    await call.message.edit_text(
        f"🧠 <b>Quiz Management</b>\n\n"
        f"Total quizzes: <b>{count}</b>\n\n"
        f"Reward system:\n"
        f"  • Every 5 correct → 🎫 1 Free Pass\n"
        f"  • Every 10 correct → 🎫 2 Free Passes",
        reply_markup=admin_quiz_kb(quizzes)
    )
    await call.answer()


@router.callback_query(F.data.startswith("qview:"))
async def adm_quiz_view(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    quiz_id = int(call.data.split(":")[1])
    quiz    = await get_quiz_by_id(quiz_id)
    if not quiz:
        await call.answer("Not found.", show_alert=True)
        return
    opts = f"🅐 {quiz['option_a']}\n🅑 {quiz['option_b']}\n🅒 {quiz['option_c']}\n🅓 {quiz['option_d']}"
    exp  = f"\n💡 {quiz['explanation']}" if quiz.get("explanation") else ""
    await call.answer(
        f"Q: {quiz['question'][:100]}\n\n{opts}\n\n✔️ {quiz['correct']}{exp}"[:200],
        show_alert=True
    )


@router.callback_query(F.data.startswith("qdel:"))
async def adm_quiz_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id): return
    quiz_id = int(call.data.split(":")[1])
    await db_delete_quiz(quiz_id)
    await call.answer("✅ Quiz deleted.", show_alert=True)
    quizzes = await get_all_quizzes()
    await call.message.edit_text(
        f"🧠 <b>Quiz Management</b>\n\nTotal: <b>{len(quizzes)}</b>",
        reply_markup=admin_quiz_kb(quizzes)
    )


# ─── ADD QUIZ WIZARD (inline, admin-only) ─────────────────────

class QuizState(StatesGroup):
    question    = State()
    option_a    = State()
    option_b    = State()
    option_c    = State()
    option_d    = State()
    correct     = State()
    explanation = State()


@router.callback_query(F.data == "qadd")
async def adm_quiz_add(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    await state.set_state(QuizState.question)
    await call.message.edit_text(
        "🧠 <b>Add Quiz — Step 1/7</b>\n\n"
        "Enter the <b>question</b>:",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(QuizState.question)
async def qs_question(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear(); return
    await state.update_data(question=message.text.strip())
    await state.set_state(QuizState.option_a)
    await message.answer("Step 2/7 — Enter <b>Option A</b>:", reply_markup=cancel_kb())


@router.message(QuizState.option_a)
async def qs_option_a(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear(); return
    await state.update_data(option_a=message.text.strip())
    await state.set_state(QuizState.option_b)
    await message.answer("Step 3/7 — Enter <b>Option B</b>:", reply_markup=cancel_kb())


@router.message(QuizState.option_b)
async def qs_option_b(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear(); return
    await state.update_data(option_b=message.text.strip())
    await state.set_state(QuizState.option_c)
    await message.answer("Step 4/7 — Enter <b>Option C</b>:", reply_markup=cancel_kb())


@router.message(QuizState.option_c)
async def qs_option_c(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear(); return
    await state.update_data(option_c=message.text.strip())
    await state.set_state(QuizState.option_d)
    await message.answer("Step 5/7 — Enter <b>Option D</b>:", reply_markup=cancel_kb())


@router.message(QuizState.option_d)
async def qs_option_d(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear(); return
    await state.update_data(option_d=message.text.strip())
    await state.set_state(QuizState.correct)
    await message.answer(
        "Step 6/7 — Which is correct?\n\nSend: <b>A</b>, <b>B</b>, <b>C</b>, or <b>D</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="A", callback_data="qcorr:A"),
            InlineKeyboardButton(text="B", callback_data="qcorr:B"),
            InlineKeyboardButton(text="C", callback_data="qcorr:C"),
            InlineKeyboardButton(text="D", callback_data="qcorr:D"),
        ]])
    )


@router.callback_query(F.data.startswith("qcorr:"))
async def qs_correct_cb(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id): return
    ans = call.data.split(":")[1]
    await state.update_data(correct=ans)
    await state.set_state(QuizState.explanation)
    await call.message.edit_text(
        f"✅ Correct answer: <b>{ans}</b>\n\n"
        f"Step 7/7 — Enter an <b>explanation</b> (shown after wrong answer)\n"
        f"Or send <code>-</code> to skip.",
        reply_markup=cancel_kb()
    )
    await call.answer()


@router.message(QuizState.correct)
async def qs_correct_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear(); return
    ans = message.text.strip().upper()
    if ans not in ("A", "B", "C", "D"):
        await message.answer("❌ Send A, B, C, or D:")
        return
    await state.update_data(correct=ans)
    await state.set_state(QuizState.explanation)
    await message.answer(
        f"✅ Correct: <b>{ans}</b>\n\n"
        "Step 7/7 — Enter <b>explanation</b> or send <code>-</code> to skip:",
        reply_markup=cancel_kb()
    )


@router.message(QuizState.explanation)
async def qs_explanation(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear(); return
    exp  = None if message.text.strip() == "-" else message.text.strip()
    data = await state.get_data()
    await state.clear()

    qid = await db_add_quiz(
        data["question"], data["option_a"], data["option_b"],
        data["option_c"], data["option_d"], data["correct"], exp
    )
    total = await get_quiz_count()
    await message.answer(
        f"✅ <b>Quiz #{qid} added!</b>\n\n"
        f"❓ {data['question']}\n\n"
        f"🅐 {data['option_a']}\n"
        f"🅑 {data['option_b']}\n"
        f"🅒 {data['option_c']}\n"
        f"🅓 {data['option_d']}\n\n"
        f"✔️ Correct: <b>{data['correct']}</b>\n"
        f"💡 {exp or '—'}\n\n"
        f"Total quizzes: <b>{total}</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Add Another", callback_data="qadd"),
            InlineKeyboardButton(text="📋 All Quizzes", callback_data="adm:quiz"),
        ]])
    )
