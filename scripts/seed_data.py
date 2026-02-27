from app.core.database import SessionLocal, engine
from app.models import Base, User
from app.core.security import hash_password
from app.services.ingestion import run_ingestion


def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if not db.query(User).filter(User.email == "demo@zeni.ai").one_or_none():
            db.add(User(email="demo@zeni.ai", password_hash=hash_password("demo1234")))
            db.commit()
        result = run_ingestion(db)
        print(f"Seed complete: {result}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
