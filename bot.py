import os
import logging
import threading
import time
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# ── CONFIGURACIÓN ──────────────────────────────────────────
# Todo se lee SOLO de variables de entorno. Nada de secretos en el código.
BOT_TOKEN = os.environ.get("BOT_TOKEN")
SOURCE_CHANNEL_ID = os.environ.get("SOURCE_CHANNEL_ID")   # VIP (origen)
DEST_CHANNEL_ID = os.environ.get("DEST_CHANNEL_ID")       # VIP Acces (destino)
RENDER_URL = os.environ.get("RENDER_URL")                 # URL pública actual del servicio en Render

_faltantes = [
    nombre for nombre, valor in [
        ("BOT_TOKEN", BOT_TOKEN),
        ("SOURCE_CHANNEL_ID", SOURCE_CHANNEL_ID),
        ("DEST_CHANNEL_ID", DEST_CHANNEL_ID),
        ("RENDER_URL", RENDER_URL),
    ] if not valor
]
if _faltantes:
    raise SystemExit(
        f"❌ Faltan variables de entorno en Render: {', '.join(_faltantes)}. "
        "Configuralas en Render → Environment antes de desplegar."
    )

SOURCE_CHANNEL_ID = int(SOURCE_CHANNEL_ID)
DEST_CHANNEL_ID = int(DEST_CHANNEL_ID)

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)


# ============ SERVIDOR DE SALUD + SELF-PING (para no dormir en el free tier) ============
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *args):
        pass


def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


def self_ping():
    """Se autopingea cada 4 minutos para no dormirse."""
    time.sleep(30)
    while True:
        try:
            requests.get(RENDER_URL, timeout=10)
            logger.info("🔔 Self-ping OK")
        except Exception as e:
            logger.warning(f"⚠️ Self-ping falló: {e}")
        time.sleep(240)


# ============ SINCRONIZACIÓN DE CANALES ============
async def sincronizar_canal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Copia cada publicación nueva del canal VIP al canal VIP Acces,
    sin etiqueta de 'reenviado' (aparece como publicación nativa)."""
    post = update.channel_post
    if post is None or post.chat.id != SOURCE_CHANNEL_ID:
        return

    try:
        await context.bot.copy_message(
            chat_id=DEST_CHANNEL_ID,
            from_chat_id=SOURCE_CHANNEL_ID,
            message_id=post.message_id,
        )
        logger.info(f"✅ Mensaje {post.message_id} copiado de VIP a VIP Acces")
    except Exception as e:
        logger.error(f"❌ Error copiando mensaje {post.message_id}: {e}")


def main():
    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=self_ping, daemon=True).start()
    logger.info("🌐 Health server y self-ping iniciados")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST, sincronizar_canal))

    logger.info("🔁 Bot de sincronización VIP → VIP Acces iniciado.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
