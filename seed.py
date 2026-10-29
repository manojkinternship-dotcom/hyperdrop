from sqlmodel import Session, select
from app.database import init_db, engine
from app.models import Customer, Rider, Order

def seed_database():
    print("Initializing database...")
    init_db()

    with Session(engine) as session:
        # Check if already seeded
        existing_orders = session.exec(select(Order)).first()
        if existing_orders:
            print("Database already contains data. Skipping re-seed.")
            return

        print("Seeding Customers...")
        c1 = Customer(
            name="Priya Sharma",
            phone="+919876543210",
            alt_phone="+919876543219",
            preferred_language="Hindi",
            saved_preferences="Prefer evening delivery after 6 PM"
        )
        c2 = Customer(
            name="Amit Verma",
            phone="+919811122233",
            alt_phone="+919811122234",
            preferred_language="English",
            saved_preferences="Leave at security gate"
        )
        c3 = Customer(
            name="Sneha Reddy",
            phone="+919844455566",
            alt_phone="+919844455567",
            preferred_language="Telugu",
            saved_preferences="Call before delivery"
        )
        session.add_all([c1, c2, c3])
        session.commit()
        session.refresh(c1)
        session.refresh(c2)
        session.refresh(c3)

        print("Seeding Riders...")
        r1 = Rider(
            name="Raju Gowda",
            phone="+919900011222",
            language="Kannada"
        )
        r2 = Rider(
            name="Muthu Kumar",
            phone="+919944433221",
            language="Tamil"
        )
        session.add_all([r1, r2])
        session.commit()
        session.refresh(r1)
        session.refresh(r2)

        print("Seeding Orders...")
        o1 = Order(
            item="Smart Watch Pro",
            value=2499.0,
            is_cod=False,
            cod_amount=0.0,
            address="Flat 402, Tower B, Prestige Palms, Whitefield, Bengaluru",
            customer_id=c1.id,
            rider_id=r1.id,
            status="out_for_delivery"
        )
        o2 = Order(
            item="Fresh Organic Groceries",
            value=650.0,
            is_cod=False,
            cod_amount=0.0,
            address="Flat 101, Wing C, Brigade Meadows, Bengaluru",
            customer_id=c2.id,
            rider_id=r1.id,
            status="out_for_delivery"
        )
        o3 = Order(
            item="Noise-Cancelling Earbuds (COD)",
            value=1299.0,
            is_cod=True,
            cod_amount=1299.0,
            address="Villa 14, Palm Avenue, Indiranagar, Bengaluru",
            customer_id=c3.id,
            rider_id=r2.id,
            status="out_for_delivery"
        )
        session.add_all([o1, o2, o3])
        session.commit()

        print("Seed completed successfully!")
        print(f"Created 3 Customers, 2 Riders, 3 Orders (1 High-Value, 1 Prepaid, 1 COD).")

if __name__ == "__main__":
    seed_database()
