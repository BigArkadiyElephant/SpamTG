import asyncio
import os
from fastapi import FastAPI, Form, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from telethon import TelegramClient
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError, SessionPasswordNeededError
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = None
phone_number = None
phone_code_hash = None
contacts_queue = []

task_status = {
    "connected": False,
    "running": False,
    "total": 0,
    "sent": 0,
    "logs": []
}

def add_log(log_type, text):
    now = datetime.now().strftime("%H:%M:%S")
    task_status["logs"].append({"time": now, "type": log_type, "text": text})

@app.get("/", response_class=FileResponse)
async def read_index():
    for path in [os.path.join(os.path.dirname(__file__), "index.html"), "index.html"]:
        if os.path.exists(path):
            return FileResponse(path)
    return HTMLResponse("<h1>Файл index.html не найден</h1>", status_code=404)

@app.get("/ws")
async def ws_status_poll():
    if client and await client.is_user_authorized():
        task_status["connected"] = True
    else:
        task_status["connected"] = False
    return task_status

@app.post("/api/auth/request-code")
async def request_code(app_id: int = Form(...), api_hash: str = Form(...), phone: str = Form(...)):
    global client, phone_number, phone_code_hash
    phone_number = phone
    
    if client:
        await client.disconnect()
        
    client = TelegramClient('crm_session', app_id, api_hash)
    await client.connect()
    
    try:
        result = await client.send_code_request(phone)
        phone_code_hash = result.phone_code_hash
        add_log("info", f"Код запрошен на номер {phone}")
        return {"status": "code_sent"}
    except Exception as e:
        add_log("err", f"Ошибка запроса кода: {str(e)}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.post("/api/auth/confirm-code")
async def confirm_code(otp: str = Form(...), password: str = Form(None)):
    global client, phone_number, phone_code_hash
    if not client or not phone_number or not phone_code_hash:
        return JSONResponse(status_code=400, content={"error": "Сессия сброшена сервером. Запросите код заново."})
    
    try:
        await client.sign_in(phone_number, otp, phone_code_hash=phone_code_hash)
        task_status["connected"] = True
        add_log("ok", "Авторизация прошла успешно!")
        return {"status": "success"}
    except SessionPasswordNeededError:
        if password:
            try:
                await client.sign_in(password=password)
                task_status["connected"] = True
                add_log("ok", "Авторизация (2FA) успешна!")
                return {"status": "success"}
            except Exception as e:
                return JSONResponse(status_code=400, content={"error": f"Неверный облачный пароль: {str(e)}"})
        return JSONResponse(status_code=202, content={"status": "password_needed", "error": "Требуется двухфакторный пароль (2FA)"})
    except Exception as e:
        add_log("err", f"Ошибка авторизации: {str(e)}")
        return JSONResponse(status_code=400, content={"error": str(e)})

@app.post("/api/auth/disconnect")
async def disconnect():
    global client
    if client:
        await client.disconnect()
    task_status["connected"] = False
    add_log("info", "Сессия завершена")
    return {"status": "disconnected"}

@app.post("/api/queue/upload")
async def upload_file(file: UploadFile = File(...)):
    global contacts_queue
    content = await file.read()
    text = content.decode('utf-8')
    contacts_queue = [line.strip() for line in text.splitlines() if line.strip()]
    task_status["total"] = len(contacts_queue)
    task_status["sent"] = 0
    task_status["logs"] = []
    return {"count": len(contacts_queue), "preview": contacts_queue[:50]}

async def mailing_worker(message: str, min_delay: int, max_delay: int):
    global client, contacts_queue
    task_status["running"] = True
    import random
    
    add_log("info", f"Запуск рассылки по {len(contacts_queue)} пользователям...")
    for i, user in enumerate(contacts_queue, start=1):
        if not task_status["running"]: break
        try:
            await client.send_message(user, message, parse_mode='markdown')
            task_status["sent"] = i
            add_log("ok", f"[{i}/{len(contacts_queue)}] Отправлено: {user}")
            if i < len(contacts_queue):
                await asyncio.sleep(random.randint(min_delay, max_delay))
        except FloodWaitError as e:
            add_log("err", f"Лимит. Спим {e.seconds} сек.")
            await asyncio.sleep(e.seconds)
        except UserPrivacyRestrictedError:
            add_log("err", f"Приватность у {user}")
            task_status["sent"] = i
        except Exception as e:
            add_log("err", f"Ошибка для {user}: {str(e)}")
            task_status["sent"] = i
    task_status["running"] = False
    add_log("ok", "Рассылка полностью завершена!")

@app.post("/api/queue/start")
async def start_mailing(background_tasks: BackgroundTasks, message: str = Form(...), min_delay: int = Form(...), max_delay: int = Form(...)):
    global client
    if not client or not await client.is_user_authorized():
        return JSONResponse(status_code=400, content={"error": "Сначала авторизуйтесь!"})
    if task_status["running"]:
        return JSONResponse(status_code=400, content={"error": "Уже запущено"})
    background_tasks.add_task(mailing_worker, message, int(min_delay), int(max_delay))
    return {"status": "started"}

@app.post("/api/queue/stop")
async def stop_mailing():
    task_status["running"] = False
    return {"status": "stopped"}
