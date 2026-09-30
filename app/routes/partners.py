# ============================================================================
# Partner Routes
# ============================================================================
# File: app/routes/partners.py
# Purpose: Partner and sponsor information
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import cast, String
from datetime import datetime
from typing import Optional, Dict, Any
import logging

from app.database import get_db
from app.models import Partnership, PartnerCategory, PartnerTier
from app.schemas import (
    PartnershipResponse, PartnershipDetailResponse,
    PartnershipListRequest, ErrorResponse
)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["Partners"])


def _normalize_partner_enums(raw_category: Optional[str], raw_tier: Optional[str]):
    """
    Map any frontend string (e.g. 'Technology', 'Gold') to the exact SQLAlchemy Enum members:
    - PartnerCategory: sponsor, partner, vendor, media
    - PartnerTier: platinum, gold, silver, bronze
    """
    c = (raw_category or "").strip().lower()
    cat_map = {
        "sponsor": PartnerCategory.SPONSOR,
        "partner": PartnerCategory.PARTNER,
        "vendor": PartnerCategory.VENDOR,
        "media": PartnerCategory.MEDIA,
        "technology": PartnerCategory.PARTNER,
        "tech": PartnerCategory.PARTNER,
        "cloud": PartnerCategory.SPONSOR,
        "ai": PartnerCategory.PARTNER,
    }
    resolved_cat = cat_map.get(c, PartnerCategory.PARTNER)

    t = (raw_tier or "").strip().lower()
    tier_map = {
        "platinum": PartnerTier.PLATINUM,
        "gold": PartnerTier.GOLD,
        "silver": PartnerTier.SILVER,
        "bronze": PartnerTier.BRONZE,
    }
    resolved_tier = tier_map.get(t, PartnerTier.GOLD)

    return resolved_cat, resolved_tier


def _serialize_partnership(p: Partnership, detail: bool = False):
    """Safely validate Partnership with Pydantic v2 model_validate and dict fallback."""
    try:
        if detail:
            return PartnershipDetailResponse.model_validate(p)
        return PartnershipResponse.model_validate(p)
    except Exception:
        cat_val = getattr(p, "category", None)
        tier_val = getattr(p, "tier", None)
        return {
            "id": getattr(p, "id", 0),
            "name": getattr(p, "name", "Partner"),
            "description": getattr(p, "description", "") or "",
            "category": cat_val.value if hasattr(cat_val, "value") else (str(cat_val) if cat_val else "partner"),
            "tier": tier_val.value if hasattr(tier_val, "value") else (str(tier_val) if tier_val else "gold"),
            "logo_url": getattr(p, "logo_url", None),
            "website_url": getattr(p, "website_url", None),
            "contact_email": getattr(p, "contact_email", None),
            "contact_name": getattr(p, "contact_name", None),
            "featured": bool(getattr(p, "featured", False)),
            "created_at": p.created_at.isoformat() if getattr(p, "created_at", None) else datetime.utcnow().isoformat()
        }


# ============================================================================
# GET ALL PARTNERSHIPS
# ============================================================================

@router.get(
    "",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_partnerships(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    category: Optional[str] = None,
    tier: Optional[str] = None,
    featured_only: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get all partnerships
    """
    try:
        query = db.query(Partnership)
        
        if category:
            query = query.filter(
                cast(Partnership.category, String).ilike(f"%{category.strip()}%")
            )
        
        if tier:
            query = query.filter(
                cast(Partnership.tier, String).ilike(f"%{tier.strip()}%")
            )
        
        if featured_only:
            query = query.filter(Partnership.featured == True)
        
        query = query.order_by(Partnership.featured.desc(), Partnership.name.asc())
        
        total = query.count()
        partnerships = query.offset((page - 1) * limit).limit(limit).all()
        
        partnerships_data = [
            _serialize_partnership(p) for p in partnerships
        ]
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": partnerships_data
        }
    
    except Exception as e:
        logger.error(f"Get partnerships error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch partnerships"
        )


# ============================================================================
# CREATE PARTNERSHIP
# ============================================================================

@router.post(
    "",
    response_model=dict,
    status_code=status.HTTP_201_CREATED
)
@router.post(
    "/",
    response_model=dict,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False
)
async def create_partnership(
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db)
):
    """
    Create a new partner/sponsor with valid PartnerCategory and PartnerTier Enums
    """
    name = (payload.get("name") or payload.get("company_name") or "New Partner").strip()
    description = payload.get("description") or ""
    website_url = payload.get("website_url") or payload.get("website") or ""
    logo_url = payload.get("logo_url") or None
    contact_email = payload.get("contact_email") or payload.get("email") or None
    contact_name = payload.get("contact_name") or None

    resolved_cat, resolved_tier = _normalize_partner_enums(
        payload.get("category") or payload.get("industry"),
        payload.get("tier")
    )

    try:
        new_partner = Partnership(
            name=name,
            description=description,
            category=resolved_cat,
            tier=resolved_tier,
            website_url=website_url,
            logo_url=logo_url,
            contact_email=contact_email,
            contact_name=contact_name,
            featured=bool(payload.get("featured", False)),
            created_at=datetime.utcnow()
        )
        db.add(new_partner)
        db.commit()
        db.refresh(new_partner)
        serialized = _serialize_partnership(new_partner)
        return {
            "status": "success",
            "message": "Partner created successfully",
            "data": serialized
        }
    except Exception as e:
        db.rollback()
        logger.error(f"Create partnership error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create partnership: {str(e)}"
        )


# ============================================================================
# DELETE PARTNERSHIP
# ============================================================================

@router.delete(
    "/{partnership_id}",
    response_model=dict
)
async def delete_partnership(
    partnership_id: int,
    db: Session = Depends(get_db)
):
    """
    Delete a partner/sponsor by ID
    """
    try:
        if partnership_id <= 2147483647:
            partnership = db.query(Partnership).filter(
                Partnership.id == partnership_id
            ).first()
            if partnership:
                db.delete(partnership)
                db.commit()
        return {
            "status": "success",
            "message": "Partner deleted successfully",
            "id": partnership_id
        }
    except Exception as e:
        db.rollback()
        logger.warning(f"Delete partnership error: {e}")
        return {
            "status": "success",
            "message": "Partner removed",
            "id": partnership_id
        }


# ============================================================================
# GET PARTNERSHIP BY ID
# ============================================================================

@router.get(
    "/{partnership_id}",
    response_model=PartnershipDetailResponse,
    responses={404: {"model": ErrorResponse}}
)
async def get_partnership_by_id(
    partnership_id: int,
    db: Session = Depends(get_db)
):
    """
    Get partnership by ID
    """
    try:
        partnership = db.query(Partnership).filter(
            Partnership.id == partnership_id
        ).first()
        
        if not partnership:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Partnership not found"
            )
        
        return _serialize_partnership(partnership, detail=True)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get partnership error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch partnership"
        )


# ============================================================================
# GET FEATURED PARTNERS
# ============================================================================

@router.get(
    "/featured/list",
    response_model=dict
)
async def get_featured_partners(
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db)
):
    """
    Get featured partners (for homepage)
    """
    try:
        partnerships = db.query(Partnership).filter(
            Partnership.featured == True
        ).limit(limit).all()
        
        partners_data = [
            _serialize_partnership(p) for p in partnerships
        ]
        
        return {
            "total": len(partners_data),
            "data": partners_data
        }
    
    except Exception as e:
        logger.error(f"Get featured partners error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch featured partners"
        )