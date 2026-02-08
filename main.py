from fastapi import FastAPI, Request, Depends, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from database import SessionLocal, engine, Base, User, Feedback, Response, UserRole, Priority, Status, Category, init_db
import bcrypt
import random
import datetime
from typing import Optional

# Initialize DB
init_db()

app = FastAPI(title="Customer Feedback Portal")

# Session Middleware for Auth
app.add_middleware(SessionMiddleware, secret_key="super-secret-key-please-change")

# Templates
templates = Jinja2Templates(directory="templates")

# Mount static (created empty directory earlier)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(request: Request, db: Session = Depends(get_db)):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()

def require_role(user: User, roles: list):
    if not user or user.role not in roles:
        return False
    return True

# Hashing
def hash_password(password: str):
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

# Seeding on Startup
@app.on_event("startup")
def startup_event():
    db = SessionLocal()
    # Check/Create Users
    if not db.query(User).first():
        users = [
            User(username="customer", password_hash=hash_password("password"), role=UserRole.CUSTOMER),
            User(username="support", password_hash=hash_password("password"), role=UserRole.SUPPORT),
            User(username="admin", password_hash=hash_password("password"), role=UserRole.ADMIN),
        ]
        db.add_all(users)
        db.commit()
        
        # Create Feedbacks
        feedbacks = []
        titles = ["Login issue", "Great feature", "Slow loading", "Color scheme", "Bug in report", "Suggestion for UI", "API error", "Export data", "Mobile view broken", "Thanks for help"]
        descriptions = ["I cannot login with my account.", "Love the new dashboard!", "Page takes 5s to load.", "Can we have dark mode?", "Report shows wrong numbers.", "Move button to left.", "500 error on /api/v1", "Need CSV export.", "Menu overlaps on phone.", "Support was very fast."]
        
        users_db = db.query(User).all()
        customer = next(u for u in users_db if u.role == UserRole.CUSTOMER)
        support = next(u for u in users_db if u.role == UserRole.SUPPORT)
        
        for i in range(10):
            fb = Feedback(
                title=titles[i],
                description=descriptions[i],
                category=random.choice(list(Category)),
                priority=random.choice(list(Priority)),
                status=random.choice(list(Status)),
                user_id=customer.id,
                created_at=datetime.datetime.utcnow() - datetime.timedelta(days=random.randint(0, 30))
            )
            feedbacks.append(fb)
        
        db.add_all(feedbacks)
        db.commit()
        
        # Create Responses
        responses = []
        for i in range(5):
            fb = random.choice(feedbacks)
            resp = Response(
                content=f"We are looking into this. (Response {i+1})",
                feedback_id=fb.id,
                user_id=support.id,
                created_at=datetime.datetime.utcnow()
            )
            responses.append(resp)
            if fb.status == Status.NEW:
                fb.status = Status.IN_REVIEW
        
        db.add_all(responses)
        db.commit()
    
    db.close()

# Routes

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def index(request: Request, user: User = Depends(get_current_user)):
    if not user:
        return RedirectResponse(url="/login")
    if user.role == UserRole.ADMIN:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/feedback")

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})
    
    request.session["user_id"] = user.id
    if user.role == UserRole.ADMIN:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/feedback", status_code=status.HTTP_302_FOUND)

@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login")

@app.get("/feedback/new", response_class=HTMLResponse)
def new_feedback_page(request: Request, user: User = Depends(get_current_user)):
    if not user: return RedirectResponse("/login")
    # Only Customer and Support can submit
    if user.role not in [UserRole.CUSTOMER, UserRole.SUPPORT]:
        return RedirectResponse("/feedback") # Or error page
        
    return templates.TemplateResponse("submit_feedback.html", {
        "request": request, 
        "user": user,
        "categories": list(Category),
        "priorities": list(Priority)
    })

@app.post("/feedback/new")
def submit_feedback(
    request: Request,
    title: str = Form(...),
    category: str = Form(...),
    description: str = Form(...),
    priority: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not user: return RedirectResponse("/login")
    
    new_fb = Feedback(
        title=title,
        category=category,
        description=description,
        priority=priority,
        user_id=user.id,
        status=Status.NEW
    )
    db.add(new_fb)
    db.commit()
    return RedirectResponse(url="/feedback", status_code=status.HTTP_302_FOUND)

@app.get("/feedback", response_class=HTMLResponse)
def feedback_list(
    request: Request, 
    category: Optional[str] = None, 
    status_filter: Optional[str] = None, 
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not user: return RedirectResponse("/login")
    
    query = db.query(Feedback)
    if category and category != "all":
        query = query.filter(Feedback.category == category)
    if status_filter and status_filter != "all":
        query = query.filter(Feedback.status == status_filter)
        
    feedbacks = query.order_by(Feedback.created_at.desc()).all()
    
    return templates.TemplateResponse("feedback_list.html", {
        "request": request,
        "user": user,
        "feedbacks": feedbacks,
        "categories": list(Category),
        "statuses": list(Status),
        "current_category": category,
        "current_status": status_filter
    })

@app.get("/feedback/{feedback_id}", response_class=HTMLResponse)
def feedback_detail(feedback_id: int, request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return RedirectResponse("/login")
    
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not fb:
        return RedirectResponse("/feedback")
        
    return templates.TemplateResponse("feedback_detail.html", {
        "request": request,
        "user": user,
        "feedback": fb,
        "statuses": list(Status)
    })

@app.post("/feedback/{feedback_id}/response")
def add_response(feedback_id: int, content: str = Form(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role not in [UserRole.SUPPORT, UserRole.ADMIN]:
        return RedirectResponse(f"/feedback/{feedback_id}")
        
    resp = Response(content=content, feedback_id=feedback_id, user_id=user.id)
    db.add(resp)
    db.commit()
    return RedirectResponse(url=f"/feedback/{feedback_id}", status_code=status.HTTP_302_FOUND)

@app.post("/feedback/{feedback_id}/status")
def update_status(feedback_id: int, status: str = Form(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user or user.role not in [UserRole.SUPPORT, UserRole.ADMIN]:
        return RedirectResponse(f"/feedback/{feedback_id}")
        
    fb = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if fb:
        fb.status = status
        if status == Status.CLOSED:
            fb.closed_at = datetime.datetime.utcnow()
        db.commit()
    return RedirectResponse(url=f"/feedback/{feedback_id}", status_code=status.HTTP_302_FOUND)

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user: return RedirectResponse("/login")
    if user.role != UserRole.ADMIN:
        return RedirectResponse("/feedback")
        
    total_feedback = db.query(Feedback).count()
    open_items = db.query(Feedback).filter(Feedback.status.in_([Status.NEW, Status.IN_REVIEW])).count()
    
    # Calculate avg resolution time
    closed_feedbacks = db.query(Feedback).filter(Feedback.status == Status.CLOSED).all()
    avg_resolution_hours = 0
    if closed_feedbacks:
        total_time = sum([(f.closed_at - f.created_at).total_seconds() for f in closed_feedbacks if f.closed_at and f.created_at])
        avg_resolution_hours = round((total_time / len(closed_feedbacks)) / 3600, 1)
        
    # Category breakdown
    cat_breakdown = {}
    for cat in Category:
        count = db.query(Feedback).filter(Feedback.category == cat).count()
        cat_breakdown[cat.value] = count

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "user": user,
        "total_feedback": total_feedback,
        "open_items": open_items,
        "avg_resolution_hours": avg_resolution_hours,
        "cat_breakdown": cat_breakdown
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
