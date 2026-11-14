import pytest
from sqlalchemy.exc import IntegrityError

from app.medical.models import MedicalRecord, MedicalRecordState


async def test_one_record_per_senior(db, add_senior):
    senior = await add_senior("+40700000201")
    for _ in range(2):
        db.add(
            MedicalRecord(
                senior_id=senior.id, storage_key="k", uploaded_by=senior.medic_id
            )
        )
    with pytest.raises(IntegrityError):
        await db.flush()


async def test_a_new_record_is_pending(db, add_senior):
    senior = await add_senior("+40700000202")
    record = MedicalRecord(
        senior_id=senior.id, storage_key="k", uploaded_by=senior.medic_id
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    assert record.state is MedicalRecordState.pending
    assert record.items is None
