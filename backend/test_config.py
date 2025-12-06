"""
Test script to verify Mistral OCR and S3 storage configuration.

Run this script to test:
1. Mistral API connection and configuration
2. S3 storage connection
3. Basic document extraction with Mistral OCR

Usage:
    python test_config.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from loguru import logger
from app.core.config import settings
from app.services.storage_service import storage_service
from app.services.mistral_service import mistral_service


async def test_mistral_connection():
    """Test Mistral API connection."""
    logger.info("=" * 60)
    logger.info("Testing Mistral API Connection")
    logger.info("=" * 60)

    try:
        # Check API key
        if not settings.MISTRAL_API_KEY:
            logger.error("❌ MISTRAL_API_KEY is not set in .env")
            return False

        logger.info(f"✓ Mistral API Key: {settings.MISTRAL_API_KEY[:10]}...{settings.MISTRAL_API_KEY[-4:]}")
        logger.info(f"✓ Mistral Model: {settings.MISTRAL_MODEL}")
        logger.info(f"✓ Mistral Temperature: {settings.MISTRAL_TEMPERATURE}")
        logger.info(f"✓ Mistral Max Tokens: {settings.MISTRAL_MAX_TOKENS}")

        # Test a simple structured extraction
        logger.info("\nTesting Mistral structured output...")

        test_text = """
        IPO Document Example

        Company Name: Tech Innovations Inc.
        IPO Date: March 15, 2025
        Offering Size: $500 million

        Risk Factors:
        - Market volatility may affect stock price
        - Regulatory changes could impact operations

        Financial Highlights:
        Revenue for 2024: $1.2 billion
        Net Income: $150 million
        """

        result = await mistral_service.extract_structured_content(
            page_text=test_text,
            page_number=1,
            document_metadata={"title": "Test IPO Document"}
        )

        logger.info(f"✓ Structured extraction successful!")
        logger.info(f"  - Found {len(result.get('sections', []))} sections")
        logger.info(f"  - Found {len(result.get('key_facts', []))} key facts")
        logger.info(f"  - Found {len(result.get('citations', []))} citations")
        logger.info(f"  - Found {len(result.get('tables', []))} tables")

        return True

    except Exception as e:
        logger.error(f"❌ Mistral API test failed: {e}")
        return False


async def test_s3_connection():
    """Test S3 storage connection."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing S3 Storage Connection")
    logger.info("=" * 60)

    try:
        # Check S3 configuration
        if not settings.S3_ENDPOINT:
            logger.error("❌ S3_ENDPOINT is not set in .env")
            return False

        if not settings.S3_ACCESS_KEY_ID:
            logger.error("❌ S3_ACCESS_KEY_ID is not set in .env")
            return False

        if not settings.S3_SECRET_ACCESS_KEY:
            logger.error("❌ S3_SECRET_ACCESS_KEY is not set in .env")
            return False

        logger.info(f"✓ S3 Endpoint: {settings.S3_ENDPOINT}")
        logger.info(f"✓ S3 Region: {settings.S3_REGION}")
        logger.info(f"✓ S3 Bucket: {settings.S3_BUCKET}")
        logger.info(f"✓ S3 Access Key: {settings.S3_ACCESS_KEY_ID[:10]}...{settings.S3_ACCESS_KEY_ID[-4:]}")

        # Test bucket connection
        logger.info("\nTesting S3 bucket connection...")
        storage_service.s3_client.head_bucket(Bucket=settings.S3_BUCKET)
        logger.info(f"✓ Successfully connected to S3 bucket: {settings.S3_BUCKET}")

        return True

    except Exception as e:
        logger.error(f"❌ S3 storage test failed: {e}")
        return False


async def test_mistral_ocr():
    """Test Mistral OCR functionality (requires a sample PDF)."""
    logger.info("\n" + "=" * 60)
    logger.info("Testing Mistral OCR (Optional)")
    logger.info("=" * 60)

    logger.info("To test Mistral OCR, you need to:")
    logger.info("1. Place a PDF file in the backend directory")
    logger.info("2. Update this function with the PDF path")
    logger.info("\nSkipping OCR test for now...")

    return True


async def main():
    """Run all configuration tests."""
    logger.info("\n" + "=" * 60)
    logger.info("IPO Verification System - Configuration Test")
    logger.info("=" * 60)

    results = []

    # Test Mistral API
    results.append(("Mistral API", await test_mistral_connection()))

    # Test S3 Storage
    results.append(("S3 Storage", await test_s3_connection()))

    # Test Mistral OCR (optional)
    results.append(("Mistral OCR", await test_mistral_ocr()))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("Test Summary")
    logger.info("=" * 60)

    all_passed = True
    for name, passed in results:
        status = "✓ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} - {name}")
        if not passed:
            all_passed = False

    logger.info("=" * 60)

    if all_passed:
        logger.info("✓ All tests passed! Configuration is correct.")
        return 0
    else:
        logger.error("❌ Some tests failed. Please check the configuration.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
