# -*- coding: utf-8 -*-
"""
Clean up non-article files from articles directory
"""

import os
from pathlib import Path


def cleanup_articles():
    """Remove non-article files"""
    output_dir = Path("articles")
    
    if not output_dir.exists():
        print("[INFO] No articles directory found")
        return
    
    # Keywords that indicate non-article content
    non_article_keywords = [
        "Pages",
        "Clear Filters",
        "Privacy Policy",
        "Contact Customer Service",
        "Create Email Alert",
        "Terms of Use",
        "Cookie Policy",
        "Sign Out",
        "Login",
        "Search",
    ]
    
    removed_count = 0
    kept_count = 0
    
    for file_path in output_dir.glob("*.txt"):
        # Skip HTML and PNG files
        if file_path.suffix in ['.html', '.png']:
            continue
        
        # Check if filename contains non-article keywords
        filename = file_path.name
        is_non_article = any(keyword in filename for keyword in non_article_keywords)
        
        if is_non_article:
            file_path.unlink()
            removed_count += 1
            print(f"[REMOVED] {filename}")
        else:
            kept_count += 1
    
    print(f"\n{'='*60}")
    print(f"[DONE] Cleanup completed!")
    print(f"   Removed: {removed_count} non-article files")
    print(f"   Kept: {kept_count} article files")
    print(f"{'='*60}")


if __name__ == "__main__":
    cleanup_articles()
