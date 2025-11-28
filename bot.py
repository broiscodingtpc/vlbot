import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ConversationHandler
from config import TELEGRAM_BOT_TOKEN, ADMIN_TELEGRAM_ID, DEV_WALLET_ADDRESS
from manager import SessionManager
import utils

# Admin check decorator
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id != ADMIN_TELEGRAM_ID:
            await update.message.reply_text("❌ Unauthorized. Admin only.")
            return
        return await func(update, context)
    return wrapper

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# States
MAIN_MENU, ENTERING_CA, CONFIRMING_TOKEN, SELECTING_STRATEGY, DEPOSITING, TRADING = range(6)

# Manager
manager = SessionManager()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db_user = manager.get_or_create_user(user.id, user.username)
    context.user_data['db_user_id'] = db_user.id
    
    # Check if user has any session (active or inactive)
    from database import get_db, Session as DBSession
    db = next(get_db())
    
    # First check for active session
    active_session = db.query(DBSession).filter(
        DBSession.user_id == db_user.id,
        DBSession.is_active == True
    ).first()
    
    if active_session:
        # User has active session - show status menu
        context.user_data['session_id'] = active_session.id
        return await show_session_menu(update, context)
    
    # If no active session, check for latest session (even if inactive)
    latest_session = db.query(DBSession).filter(
        DBSession.user_id == db_user.id
    ).order_by(DBSession.id.desc()).first()
    
    if latest_session:
        # User has a session (even if inactive) - show it so they can withdraw
        context.user_data['session_id'] = latest_session.id
        return await show_session_menu(update, context)
    else:
        # New user or no active session - show welcome
        welcome_text = (
            "🔥 **KodeS Volume Bot** 🔥\n\n"
            "The **MOST AFFORDABLE** volume generation solution on Solana!\n\n"
            "📢 **Official Channel:** [Kodeprint](https://t.me/Kodeprint)\n"
            "_Join for Token Calls, Updates & Community!_\n\n"
            "**💎 Why Volume Matters?**\n"
            "📈 **Trending Power**: High volume = Trending status on DexScreener, Birdeye & Jupiter\n"
            "🚀 **Investor Magnet**: Real trading activity attracts serious investors\n"
            "🤖 **Algorithm Boost**: Consistent volume triggers positive sentiment bots\n\n"
            "**⚡ Our Unique Advantage:**\n"
            "💰 **TOKEN-BASED VOLUME**: We use YOUR tokens for volume, NOT expensive SOL!\n"
            "💵 **ULTRA CHEAP**: Generate massive volume with minimal cost\n"
            "🎯 **Smart Trading**: Randomized patterns that look 100% organic\n"
            "🔐 **Multi-Wallet System**: Unique wallets prevent detection & clustering\n"
            "⚙️ **Fully Automated**: Set it and forget it - we handle everything\n\n"
            "**Ready to boost your token to the moon?** 🚀"
        )
        
        keyboard = [
            [InlineKeyboardButton("🚀 Start Volume Session", callback_data='new_session')],
            [InlineKeyboardButton("💰 Withdraw Funds", callback_data='withdraw_menu')],
            [InlineKeyboardButton("📢 Join Channel", url='https://t.me/Kodeprint')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.callback_query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
        
        return MAIN_MENU
    
    status_emoji = "🟢" if session.is_active else "🔴"
    status_text = "RUNNING" if session.is_active else "PAUSED"
    
    menu_text = (
        f"{status_emoji} **KodeS Volume Bot - Active Session**\n\n"
        f"**Target Token**\n"
        f"📍 CA: `{session.token_ca}`\n"
        f"💎 Strategy: **{session.strategy.upper()}**\n\n"
        f"**📊 Performance Metrics**\n"
        f"💰 Total Volume Generated: **${session.total_volume_generated:,.2f}**\n"
        f"⚡ Status: **{status_text}**\n\n"
        "**🎮 Control Center:**"
    )
    
    keyboard = [
        [InlineKeyboardButton("📊 Live Statistics", callback_data='check_status')],
        [InlineKeyboardButton("⚙️ Strategy Settings", callback_data='settings')],
        [InlineKeyboardButton("🛑 Stop & Withdraw", callback_data='withdraw_menu')],
        [InlineKeyboardButton("🔄 Start New Session", callback_data='new_session')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.callback_query.edit_message_text(menu_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    return MAIN_MENU

async def new_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        "📝 **Start New Volume Session**\n\n"
        "Enter the **Contract Address (CA)** of your token.\n\n"
        "💡 *Tip: Token needs at least $1k liquidity on Raydium/Jupiter for best results.*\n\n"
        "💰 *Remember: We use YOUR tokens for volume - no expensive SOL needed!*"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Cancel", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    return ENTERING_CA

async def receive_ca(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ca = update.message.text.strip()
    
    if len(ca) < 30:
        await update.message.reply_text("❌ Invalid CA. Please try again.")
        return ENTERING_CA
    
    info = utils.get_token_info(ca)
    
    if info:
        mcap_fmt = f"${float(info['mcap']):,.0f}"
        liq_fmt = f"${float(info['liquidity']):,.0f}"
        price_fmt = f"${float(info['price']):.8f}"
        symbol = info['symbol']
        
        token_info = (
            f"🔍 **Token Found: {symbol}**\n\n"
            f"📍 CA: `{ca}`\n"
            f"💵 Price: {price_fmt}\n"
            f"📊 Market Cap: {mcap_fmt}\n"
            f"💧 Liquidity: {liq_fmt}\n\n"
            "**Is this the correct token?**"
        )
        
        context.user_data['pending_ca'] = ca
        context.user_data['token_symbol'] = symbol
    else:
        token_info = (
            f"⚠️ **Token Info Not Found**\n\n"
            f"📍 CA: `{ca}`\n\n"
            "Could not fetch data from DexScreener.\n"
            "**Do you want to proceed anyway?**"
        )
        context.user_data['pending_ca'] = ca
        context.user_data['token_symbol'] = "Unknown"
    
    keyboard = [
        [InlineKeyboardButton("✅ Yes, Continue", callback_data='confirm_token')],
        [InlineKeyboardButton("❌ No, Re-enter CA", callback_data='new_session')],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(token_info, reply_markup=reply_markup, parse_mode='Markdown')
    return CONFIRMING_TOKEN

async def confirm_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    ca = context.user_data.get('pending_ca')
    symbol = context.user_data.get('token_symbol', 'Unknown')
    
    user_id = context.user_data.get('db_user_id')
    session = manager.create_session(user_id, ca)
    context.user_data['session_id'] = session.id
    
    text = (
        f"✅ **Token Confirmed: {symbol}**\n\n"
        "🎯 Select your volume generation strategy:\n\n"
        "💡 *Remember: We use YOUR tokens for volume - no expensive SOL needed!*"
    )
    
    keyboard = [
        [InlineKeyboardButton("🐢 Slow (Organic)", callback_data='slow')],
        [InlineKeyboardButton("🐇 Medium (Balanced)", callback_data='medium')],
        [InlineKeyboardButton("🚀 Fast (Aggressive)", callback_data='fast')],
        [InlineKeyboardButton("🔙 Back", callback_data='new_session')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    return SELECTING_STRATEGY

async def select_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    strategy = query.data
    session_id = context.user_data.get('session_id')
    manager.update_strategy(session_id, strategy)
    
    session = manager.get_session(session_id)
    
    deposit_text = (
        f"✅ Strategy: **{strategy.upper()}** selected.\n\n"
        "💰 **Deposit Your Tokens**\n\n"
        "Send your **TOKENS** + **0.1 SOL** (for gas) to:\n\n"
        f"`{session.deposit_wallet_address}`\n\n"
        "_(Tap to copy)_\n\n"
        "💡 *We use YOUR tokens to generate volume - that's why we're so cheap!*\n\n"
        "Once sent, click **Check Deposit** below."
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Check Deposit", callback_data='check_deposit')],
        [InlineKeyboardButton("🔙 Back", callback_data='confirm_token')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(deposit_text, reply_markup=reply_markup, parse_mode='Markdown')
    return DEPOSITING

async def check_deposit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    session_id = context.user_data.get('session_id')
    has_funds, message = manager.check_deposit(session_id)
    
    if has_funds:
        await query.edit_message_text("✅ **Deposit Confirmed!**\n\n🚀 Starting KodeS Volume Bot...")
        
        # Define callback for periodic updates
        async def send_update(msg):
            try:
                await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode='Markdown')
            except Exception as e:
                logging.error(f"Failed to send update to {update.effective_chat.id}: {e}")

        await manager.start_trading_session(
            session_id, 
            notification_callback=send_update,
            telegram_chat_id=update.effective_chat.id
        )
        
        text = (
            "🟢 **KodeS Volume Bot is ACTIVE!**\n\n"
            "🚀 Your token volume is now being generated!\n\n"
            "📊 You'll receive performance updates every 5 minutes.\n"
            "💰 Use `/withdraw <address>` to stop and withdraw funds.\n\n"
            "💎 *Generating volume with YOUR tokens - the affordable way!*"
        )
        
        await query.edit_message_text(text, parse_mode='Markdown')
        return TRADING
    else:
        await query.answer(message, show_alert=True)
        return DEPOSITING

async def withdraw_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = (
        "💰 **Withdraw Your Funds**\n\n"
        "Enter your wallet address to withdraw all remaining tokens and SOL.\n\n"
        "Format: `/withdraw <your_wallet_address>`\n\n"
        "⚠️ *This will stop the volume generation and return all funds.*"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text("⚠️ Usage: `/withdraw <your_wallet_address>`", parse_mode='Markdown')
        return
        
    recipient = context.args[0]
    
    from database import get_db, Session as DBSession, User
    db = next(get_db())
    db_user = db.query(User).filter(User.telegram_id == str(user.id)).first()
    
    if not db_user:
        await update.message.reply_text("❌ No sessions found. Please /start first.")
        return
        
    # Try to use session from context first, otherwise get latest
    session_id = None
    if hasattr(update, 'effective_message') and update.effective_message:
        # Check if we have session_id in context
        pass
    
    latest_session = db.query(DBSession).filter(DBSession.user_id == db_user.id).order_by(DBSession.id.desc()).first()
    
    if not latest_session:
        await update.message.reply_text("❌ No sessions found.")
        return
    
    msg = await update.message.reply_text(f"🛑 Sweeping funds to `{recipient}`...", parse_mode='Markdown')
    
    report = await manager.sweep_session_funds(latest_session.id, recipient)
    
    if report:
        await msg.edit_text(f"✅ **Withdrawal Complete**\n\n{report}", parse_mode='Markdown')
    else:
        await msg.edit_text("⚠️ No funds found to withdraw.")

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await start(update, context)

async def check_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detailed session status."""
    query = update.callback_query
    await query.answer()
    
    session_id = context.user_data.get('session_id')
    session = manager.get_session(session_id)
    
    if not session:
        await query.edit_message_text("❌ Session not found.")
        return MAIN_MENU
    
    # Get wallet balances
    from database import get_db, SubWallet
    db = next(get_db())
    sub_wallets = db.query(SubWallet).filter(SubWallet.session_id == session.id).all()
    
    total_sol = utils.get_balance(session.deposit_wallet_address)
    total_tokens = utils.get_token_balance(session.deposit_wallet_address, session.token_ca)
    
    for sw in sub_wallets:
        total_sol += utils.get_balance(sw.address)
        total_tokens += utils.get_token_balance(sw.address, session.token_ca)
    
    status_text = (
        f"📊 **KodeS Volume Bot - Live Status**\n\n"
        f"📍 Token: `{session.token_ca}`\n"
        f"⚡ Strategy: {session.strategy.upper()}\n"
        f"🟢 Status: {'🟢 ACTIVE' if session.is_active else '🔴 INACTIVE'}\n\n"
        f"💰 **Current Balances:**\n"
        f"💵 SOL: {total_sol:.4f}\n"
        f"🪙 Tokens: {total_tokens:,.2f}\n\n"
        f"📈 **Volume Generated:** ${session.total_volume_generated:,.2f}\n"
        f"👛 Active Wallets: {len(sub_wallets) + 1}\n\n"
        f"💎 *Using YOUR tokens for volume - the affordable way!*"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(status_text, reply_markup=reply_markup, parse_mode='Markdown')
    return MAIN_MENU

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings menu."""
    query = update.callback_query
    await query.answer()
    
    session_id = context.user_data.get('session_id')
    session = manager.get_session(session_id)
    
    if not session:
        await query.edit_message_text("❌ Session not found.")
        return MAIN_MENU
    
    settings_text = (
        f"⚙️ **KodeS Volume Bot - Settings**\n\n"
        f"📍 Current Token: `{session.token_ca[:8]}...`\n"
        f"⚡ Current Strategy: {session.strategy.upper()}\n\n"
        "What would you like to change?"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Change Strategy", callback_data='change_strategy')],
        [InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(settings_text, reply_markup=reply_markup, parse_mode='Markdown')
    return MAIN_MENU

async def change_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change trading strategy."""
    query = update.callback_query
    await query.answer()
    
    text = "⚡ **Select New Strategy:**"
    
    keyboard = [
        [InlineKeyboardButton("🐢 Slow (Organic)", callback_data='set_slow')],
        [InlineKeyboardButton("🐇 Medium (Balanced)", callback_data='set_medium')],
        [InlineKeyboardButton("🚀 Fast (Aggressive)", callback_data='set_fast')],
        [InlineKeyboardButton("🔙 Back", callback_data='settings')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    return MAIN_MENU

async def set_strategy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Update strategy."""
    query = update.callback_query
    await query.answer()
    
    new_strategy = query.data.replace('set_', '')
    session_id = context.user_data.get('session_id')
    
    manager.update_strategy(session_id, new_strategy)
    
    await query.answer(f"✅ Strategy updated to {new_strategy.upper()}!", show_alert=True)
    return await settings(update, context)

async def delete_session_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete/reset incomplete session."""
    query = update.callback_query
    await query.answer()
    
    session_id = context.user_data.get('session_id')
    if not session_id:
        await query.edit_message_text("❌ No session found.")
        return MAIN_MENU
    
    # Mark session as inactive
    success = manager.delete_session(session_id)
    
    if success:
        # Clear session from context
        context.user_data.pop('session_id', None)
        await query.edit_message_text(
            "✅ **Session Deleted**\n\n"
            "The incomplete session has been reset.\n"
            "You can now start a new session.",
            parse_mode='Markdown'
        )
        # Return to start menu
        await asyncio.sleep(1)
        return await start(update, context)
    else:
        await query.edit_message_text("❌ Failed to delete session.")
        return MAIN_MENU

# ===== ADMIN COMMANDS =====

@admin_only
async def admin_sweep_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sweep all remaining funds from all sessions to dev wallet."""
    from database import get_db, Session as DBSession
    
    db = next(get_db())
    all_sessions = db.query(DBSession).all()
    
    if not all_sessions:
        await update.message.reply_text("No sessions found.")
        return
    
    msg = await update.message.reply_text(f"🔄 Sweeping {len(all_sessions)} sessions to dev wallet...")
    
    total_report = []
    for session in all_sessions:
        report = await manager.sweep_session_funds(session.id, DEV_WALLET_ADDRESS)
        if report:
            total_report.append(f"**Session {session.id}:**\n{report}")
    
    if total_report:
        full_report = "\n\n".join(total_report)
        await msg.edit_text(f"✅ **Admin Sweep Complete**\n\n{full_report}", parse_mode='Markdown')
    else:
        await msg.edit_text("⚠️ No funds found in any session.")

@admin_only
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show global statistics."""
    from database import get_db, Session as DBSession, User
    
    db = next(get_db())
    total_users = db.query(User).count()
    total_sessions = db.query(DBSession).count()
    active_sessions = db.query(DBSession).filter(DBSession.is_active == True).count()
    
    stats = (
        f"📊 **Admin Statistics**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"📝 Total Sessions: {total_sessions}\n"
        f"🟢 Active Sessions: {active_sessions}\n"
        f"🔴 Inactive: {total_sessions - active_sessions}"
    )
    
    await update.message.reply_text(stats, parse_mode='Markdown')

@admin_only
async def admin_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all sessions."""
    from database import get_db, Session as DBSession, User
    
    db = next(get_db())
    sessions = db.query(DBSession).order_by(DBSession.id.desc()).limit(20).all()
    
    if not sessions:
        await update.message.reply_text("No sessions found.")
        return
    
    lines = ["📋 **Recent Sessions (Last 20)**\n"]
    for s in sessions:
        user = db.query(User).filter(User.id == s.user_id).first()
        status = "🟢" if s.is_active else "🔴"
        lines.append(
            f"{status} **ID {s.id}** | User: {user.username or 'N/A'}\n"
            f"Token: `{s.token_ca[:8]}...` | Strategy: {s.strategy}"
        )
    
    await update.message.reply_text("\n\n".join(lines), parse_mode='Markdown')

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not found in environment variables.")
        return

    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(new_session, pattern='^new_session$'),
                CallbackQueryHandler(withdraw_menu, pattern='^withdraw_menu$'),
                CallbackQueryHandler(check_status, pattern='^check_status$'),
                CallbackQueryHandler(settings, pattern='^settings$'),
                CallbackQueryHandler(change_strategy, pattern='^change_strategy$'),
                CallbackQueryHandler(set_strategy, pattern='^set_(slow|medium|fast)$'),
                CallbackQueryHandler(delete_session_handler, pattern='^delete_session$'),
                CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'),
            ],
            ENTERING_CA: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_ca),
                CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$')
            ],
            CONFIRMING_TOKEN: [
                CallbackQueryHandler(confirm_token, pattern='^confirm_token$'),
                CallbackQueryHandler(new_session, pattern='^new_session$'),
                CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$')
            ],
            SELECTING_STRATEGY: [
                CallbackQueryHandler(select_strategy, pattern='^(slow|medium|fast)$'),
                CallbackQueryHandler(confirm_token, pattern='^confirm_token$')
            ],
            DEPOSITING: [
                CallbackQueryHandler(check_deposit, pattern='^check_deposit$'),
                CallbackQueryHandler(confirm_token, pattern='^confirm_token$')
            ],
            TRADING: [
                CallbackQueryHandler(withdraw_menu, pattern='^withdraw_menu$'),
                CallbackQueryHandler(check_status, pattern='^check_status$'),
                CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$'),
            ]
        },
        fallbacks=[
            CommandHandler('start', start),
            CallbackQueryHandler(back_to_menu, pattern='^back_to_menu$')
        ],
        per_message=False
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('withdraw', withdraw))

if __name__ == '__main__':
    main()
