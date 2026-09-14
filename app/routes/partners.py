# ============================================================================
# Partner Routes
# ============================================================================
# File: app/routes/partners.py
# Purpose: Partner and sponsor information
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
import logging

from app.database import get_db
from app.models import Partnership
from app.schemas import (
    PartnershipResponse, PartnershipDetailResponse,
    PartnershipListRequest, ErrorResponse
)


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/partnerships", tags=["Partnerships"])


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
    
    Args:
        page: Page number
        limit: Results per page
        category: Filter by category
        tier: Filter by tier
        featured_only: Show only featured partners
        db: Database session
    
    Returns:
        dict: Paginated partnerships list
    """
    try:
        query = db.query(Partnership)
        
        if category:
            query = query.filter(Partnership.category == category)
        
        if tier:
            query = query.filter(Partnership.tier == tier)
        
        if featured_only:
            query = query.filter(Partnership.featured == True)
        
        query = query.order_by(Partnership.featured.desc(), Partnership.name.asc())
        
        total = query.count()
        partnerships = query.offset((page - 1) * limit).limit(limit).all()
        
        partnerships_data = [
            PartnershipResponse.from_attributes(p) for p in partnerships
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
    
    Args:
        partnership_id: Partnership ID
        db: Database session
    
    Returns:
        PartnershipDetailResponse: Partnership details
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
        
        return PartnershipDetailResponse.from_attributes(partnership)
    
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
    
    Args:
        limit: Number of featured partners
        db: Database session
    
    Returns:
        dict: Featured partnerships
    """
    try:
        partnerships = db.query(Partnership).filter(
            Partnership.featured == True
        ).limit(limit).all()
        
        partners_data = [
            PartnershipResponse.from_attributes(p) for p in partnerships
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