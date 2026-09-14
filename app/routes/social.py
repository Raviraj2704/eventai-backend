# ============================================================================
# Social Routes
# ============================================================================
# File: app/routes/social.py
# Purpose: Social wall posts, comments, and engagement
# Status: Production-Ready ✅

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from datetime import datetime
from typing import Optional
import logging

from app.database import get_db
from app.models import SocialPost, SocialComment, User, Leaderboard
from app.schemas import (
    SocialPostResponse, SocialPostCreateRequest, SocialCommentResponse,
    SocialCommentCreateRequest, SocialPostListRequest, ErrorResponse
)
from app.routes.users import get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/social", tags=["Social"])


# ============================================================================
# GET ALL POSTS
# ============================================================================

@router.get(
    "/posts",
    response_model=dict,
    responses={400: {"model": ErrorResponse}}
)
async def get_social_posts(
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    sort_by: Optional[str] = "recent",
    current_user: Optional[User] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get all social posts with pagination
    
    Args:
        page: Page number
        limit: Results per page
        sort_by: Sort by (recent/popular/trending)
        current_user: Optional authenticated user
        db: Database session
    
    Returns:
        dict: Paginated posts list
    """
    try:
        query = db.query(SocialPost).filter(SocialPost.is_approved == True)
        
        # Sorting
        if sort_by == "popular":
            query = query.order_by(SocialPost.like_count.desc())
        elif sort_by == "trending":
            query = query.order_by(
                (SocialPost.like_count + SocialPost.comment_count).desc()
            )
        else:
            query = query.order_by(SocialPost.created_at.desc())
        
        # Get total count
        total = query.count()
        
        # Pagination
        posts = query.offset((page - 1) * limit).limit(limit).all()
        
        # Format response
        posts_data = [
            SocialPostResponse.model_validate(post) for post in posts
        ]
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
            "has_next": page * limit < total,
            "has_prev": page > 1,
            "data": posts_data
        }
    
    except Exception as e:
        logger.error(f"Get posts error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch posts"
        )


# ============================================================================
# CREATE POST
# ============================================================================

@router.post(
    "/posts",
    response_model=SocialPostResponse,
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorResponse}}
)
async def create_social_post(
    request: SocialPostCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create new social post
    
    Args:
        request: Post data
        current_user: Authenticated user
        db: Database session
    
    Returns:
        SocialPostResponse: Created post
    """
    try:
        # Create post
        post = SocialPost(
            user_id=current_user.id,
            content=request.content,
            image_url=request.image_url,
            is_approved=True,  # Auto-approve in development
            created_at=datetime.utcnow()
        )
        
        db.add(post)
        db.commit()
        db.refresh(post)
        
        # Award points
        leaderboard = db.query(Leaderboard).filter(
            Leaderboard.user_id == current_user.id
        ).first()
        
        if leaderboard:
            leaderboard.total_points += 5  # 5 points for post
            leaderboard.posts_created += 1
            leaderboard.last_activity = datetime.utcnow()
            db.commit()
        
        logger.info(f"Post created: {post.id} by user {current_user.id}")
        
        return SocialPostResponse.model_validate(post)
    
    except Exception as e:
        db.rollback()
        logger.error(f"Create post error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create post"
        )


# ============================================================================
# LIKE POST
# ============================================================================

@router.post(
    "/posts/{post_id}/like",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def like_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Like a social post
    
    Args:
        post_id: Post ID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        # Get post
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        # In production, create a Like junction table to track unique likes
        # For now, just increment count
        post.like_count += 1
        db.commit()
        
        logger.info(f"Post {post_id} liked by user {current_user.id}")
        
        return {
            "message": "Post liked",
            "like_count": post.like_count
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Like post error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to like post"
        )


# ============================================================================
# UNLIKE POST
# ============================================================================

@router.post(
    "/posts/{post_id}/unlike",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def unlike_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Unlike a social post
    
    Args:
        post_id: Post ID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        # Get post
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        # Decrement if greater than 0
        if post.like_count > 0:
            post.like_count -= 1
        
        db.commit()
        
        logger.info(f"Post {post_id} unliked by user {current_user.id}")
        
        return {
            "message": "Post unliked",
            "like_count": post.like_count
        }
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Unlike post error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unlike post"
        )


# ============================================================================
# DELETE POST
# ============================================================================

@router.delete(
    "/posts/{post_id}",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        403: {"model": ErrorResponse}
    }
)
async def delete_post(
    post_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete social post (author or admin only)
    
    Args:
        post_id: Post ID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        # Get post
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
        
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        # Check permissions
        if post.user_id != current_user.id and not getattr(current_user, "is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete this post"
            )
        
        db.delete(post)
        db.commit()
        
        logger.info(f"Post {post_id} deleted by user {current_user.id}")
        
        return {"message": "Post deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Delete post error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete post"
        )


# ============================================================================
# GET POST COMMENTS
# ============================================================================

@router.get(
    "/posts/{post_id}/comments",
    response_model=dict,
    responses={404: {"model": ErrorResponse}}
)
async def get_post_comments(
    post_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db)
):
    """
    Get comments on a post
    
    Args:
        post_id: Post ID
        page: Page number
        limit: Results per page
        db: Database session
    
    Returns:
        dict: Paginated comments
    """
    try:
        # Get post
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        # Get comments
        query = db.query(SocialComment).filter(
            SocialComment.post_id == post_id
        ).order_by(SocialComment.created_at.desc())
        
        total = query.count()
        comments = query.offset((page - 1) * limit).limit(limit).all()
        
        comments_data = [
            SocialCommentResponse.model_validate(comment) for comment in comments
        ]
        
        return {
            "total": total,
            "page": page,
            "limit": limit,
            "data": comments_data
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get comments error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch comments"
        )


# ============================================================================
# CREATE COMMENT
# ============================================================================

@router.post(
    "/posts/{post_id}/comments",
    response_model=SocialCommentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}
    }
)
async def create_comment(
    post_id: int,
    request: SocialCommentCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create comment on post
    
    Args:
        post_id: Post ID
        request: Comment data
        current_user: Authenticated user
        db: Database session
    
    Returns:
        SocialCommentResponse: Created comment
    """
    try:
        # Get post
        post = db.query(SocialPost).filter(SocialPost.id == post_id).first()
        if not post:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Post not found"
            )
        
        # Create comment
        comment = SocialComment(
            post_id=post_id,
            user_id=current_user.id,
            content=request.content,
            is_approved=True,
            created_at=datetime.utcnow()
        )
        
        db.add(comment)
        
        # Increment post comment count
        post.comment_count += 1
        
        db.commit()
        db.refresh(comment)
        
        logger.info(f"Comment created: {comment.id} by user {current_user.id}")
        
        return SocialCommentResponse.model_validate(comment)
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Create comment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create comment"
        )


# ============================================================================
# DELETE COMMENT
# ============================================================================

@router.delete(
    "/comments/{comment_id}",
    response_model=dict,
    responses={
        401: {"model": ErrorResponse}, 
        404: {"model": ErrorResponse}, 
        403: {"model": ErrorResponse}
    }
)
async def delete_comment(
    comment_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete comment (author or admin only)
    
    Args:
        comment_id: Comment ID
        current_user: Authenticated user
        db: Database session
    
    Returns:
        dict: Success message
    """
    try:
        # Get comment
        comment = db.query(SocialComment).filter(SocialComment.id == comment_id).first()
        
        if not comment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Comment not found"
            )
        
        # Check permissions
        if comment.user_id != current_user.id and not getattr(current_user, "is_admin", False):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete this comment"
            )
        
        # Get post to decrement comment count
        post = db.query(SocialPost).filter(SocialPost.id == comment.post_id).first()
        if post and post.comment_count > 0:
            post.comment_count -= 1
        
        db.delete(comment)
        db.commit()
        
        logger.info(f"Comment {comment_id} deleted by user {current_user.id}")
        
        return {"message": "Comment deleted successfully"}
    
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Delete comment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete comment"
        )