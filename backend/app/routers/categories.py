from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.category import Category, CategorySpecDefinition
from app.auth import get_current_user, filter_by_ownership, check_ownership
from app.services.product_category_helper import delete_category_cascade
from app.schemas.category import CategoryCreate, CategoryUpdate, SpecDefinitionCreate, SpecDefinitionUpdate

router = APIRouter()


@router.get("/categories")
def list_categories(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    page: int = 1,
    per_page: int = 50,
):
    all_cats = filter_by_ownership(db.query(Category), Category, user).order_by(Category.sort_order, Category.id).all()
    cat_dicts = [c.to_dict() for c in all_cats]

    # Flatten tree: parent immediately followed by its children
    def flatten(parent_id=None):
        result = []
        for c in cat_dicts:
            if c["parent_id"] == parent_id:
                result.append(c)
                result.extend(flatten(c["id"]))
        return result

    flat = flatten(None)
    # Include any orphaned children (parent deleted)
    seen = {c["id"] for c in flat}
    for c in cat_dicts:
        if c["id"] not in seen:
            flat.append(c)

    total = len(flat)
    paged = flat[(page - 1) * per_page : page * per_page]
    return {"categories": paged, "total": total, "page": page, "per_page": per_page}


@router.get("/categories/tree")
def category_tree(db: Session = Depends(get_db), user=Depends(get_current_user)):
    cats = db.query(Category).order_by(Category.sort_order, Category.id).all()
    cat_dicts = [c.to_dict() for c in cats]

    def build_tree(parent_id=None):
        return [
            {**c, "children": build_tree(c["id"])}
            for c in cat_dicts
            if (c["parent_id"] is None and parent_id is None) or c["parent_id"] == parent_id
        ]

    return {"tree": build_tree(None)}


@router.post("/categories")
def create_category(data: CategoryCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    slug = data.slug or data.name.lower().replace(" ", "-")
    # Ensure uniqueness
    base_slug = slug
    cnt = 1
    while db.query(Category).filter_by(slug=slug).first():
        slug = f"{base_slug}-{cnt}"
        cnt += 1
    cat = Category(
        name=data.name,
        slug=slug,
        parent_id=data.parent_id,
        level=data.level,
        sort_order=data.sort_order,
        created_by=user.id,
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return {"category": cat.to_dict()}


@router.put("/categories/{cat_id}")
def update_category(cat_id: int, data: CategoryUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    cat = db.get(Category, cat_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    check_ownership(cat, user)
    for field in ["name", "slug", "parent_id", "level", "sort_order", "is_active"]:
        val = getattr(data, field, None)
        if val is not None:
            setattr(cat, field, val)
    db.commit()
    return {"category": cat.to_dict()}


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    cat = db.get(Category, cat_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    check_ownership(cat, user)

    # Cascade-delete child records to avoid FK violations
    from app.models.product import Product
    from app.models.mapping import ProductCommMethod, ProductCommProtocol, ProductPowerSupply
    from app.models.mapping import ProductHardwareInterface, ProductSensorCapability, ProductImage
    from app.models.dependency import ProductDependency
    from app.models.quotation import QuotationItem
    from app.models.solution import SolutionItem

    db.execute(text('DELETE FROM category_spec_definitions WHERE category_id = :cid'), {'cid': cat_id})
    delete_category_cascade(db, cat_id)
    db.execute(text('DELETE FROM product_dependencies WHERE depends_on_category_id = :cid'), {'cid': cat_id})
    # Update products using old single-category column (NOT NULL, fallback to first category)
    fallback = db.query(Category).filter(Category.id != cat_id, Category.is_active == True).first()
    fallback_id = fallback.id if fallback else 1
    db.execute(text('UPDATE products SET category_id = :fid WHERE category_id = :cid'),
               {'cid': cat_id, 'fid': fallback_id})
    db.execute(text('UPDATE device_categories SET parent_id = NULL WHERE parent_id = :cid'), {'cid': cat_id})

    db.delete(cat)
    db.commit()
    return {"ok": True}


# Spec Definitions
@router.get("/categories/{cat_id}/spec-definitions")
def list_spec_defs(cat_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    defs = db.query(CategorySpecDefinition).filter_by(category_id=cat_id)\
        .order_by(CategorySpecDefinition.sort_order).all()
    return {"spec_definitions": [sd.to_dict() for sd in defs]}


@router.post("/categories/{cat_id}/spec-definitions")
def create_spec_def(cat_id: int, data: SpecDefinitionCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    cat = db.get(Category, cat_id)
    if not cat:
        raise HTTPException(404, "Category not found")
    sd = CategorySpecDefinition(
        category_id=cat_id,
        spec_key=data.spec_key,
        display_name=data.display_name,
        spec_type=data.spec_type,
        unit=data.unit,
        sort_order=data.sort_order,
        is_filterable=data.is_filterable,
        is_comparable=data.is_comparable,
        display_group=data.display_group,
        options=data.options,
        validation=data.validation,
    )
    db.add(sd)
    db.commit()
    db.refresh(sd)
    return {"spec_definition": sd.to_dict()}


@router.put("/categories/{cat_id}/spec-definitions/{spec_id}")
def update_spec_def(cat_id: int, spec_id: int, data: SpecDefinitionUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sd = db.get(CategorySpecDefinition, spec_id)
    if not sd or sd.category_id != cat_id:
        raise HTTPException(404, "Spec definition not found")
    fields = ["spec_key", "display_name", "spec_type", "unit", "sort_order",
              "is_filterable", "is_comparable", "display_group", "options", "validation"]
    for f in fields:
        val = getattr(data, f, None)
        if val is not None:
            setattr(sd, f, val)
    db.commit()
    return {"spec_definition": sd.to_dict()}


@router.delete("/categories/{cat_id}/spec-definitions/{spec_id}")
def delete_spec_def(cat_id: int, spec_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    sd = db.get(CategorySpecDefinition, spec_id)
    if not sd or sd.category_id != cat_id:
        raise HTTPException(404, "Spec definition not found")
    db.delete(sd)
    db.commit()
    return {"ok": True}
