# Contributing to PenipuMY

Thank you for your interest in contributing! This document provides guidelines for contributing to this project.

## 🤝 How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:
- Clear title and description
- Steps to reproduce
- Expected vs actual behavior
- Screenshots (if applicable)
- Python version and OS

### Suggesting Features

Feature requests are welcome! Please:
- Check if the feature already exists or has been requested
- Clearly describe the feature and its benefits
- Provide use cases

### Pull Requests

1. **Fork the Repository**
   ```bash
   git clone https://github.com/affifuddin-hazam/PenipuMY.git
   cd PenipuMY
   ```

2. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make Your Changes**
   - Write clean, readable code
   - Follow the coding standards below
   - Test your changes

4. **Commit Your Changes**
   ```bash
   git add .
   git commit -m "Add: brief description of your changes"
   ```

   Commit message format:
   - `Add:` for new features
   - `Fix:` for bug fixes
   - `Update:` for updates to existing features
   - `Refactor:` for code refactoring
   - `Docs:` for documentation changes

5. **Push to GitHub**
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create a Pull Request**
   - Go to GitHub and create a PR
   - Fill out the PR template
   - Wait for review

## 📝 Coding Standards

### Python Style Guide

- Follow [PEP 8](https://pep8.org/)
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions small and focused
- Use type hints where appropriate

### Code Example

```python
def search_phone_number(phone: str, user_id: int) -> dict:
    """
    Search for a phone number across multiple sources.

    Args:
        phone: The phone number to search
        user_id: Telegram user ID making the request

    Returns:
        Dictionary containing search results from all sources

    Example:
        >>> search_phone_number("0123456789", 12345)
        {'status': 'success', 'results': [...]}
    """
    # Implementation here
    pass
```

### File Organization

- Keep related functionality in separate modules
- Use clear, descriptive file names
- Follow the existing project structure

### Documentation

- Update README.md if adding new features
- Add inline comments for complex logic
- Update docstrings when modifying functions

## 🧪 Testing

Before submitting a PR:

1. **Test Manually**
   - Run the bot locally
   - Test your feature thoroughly
   - Try edge cases

2. **Check for Errors**
   - No Python syntax errors
   - No runtime exceptions
   - Handles errors gracefully

3. **Code Quality**
   ```bash
   # Check for common issues
   pylint your_file.py

   # Format code
   black your_file.py
   ```

## 🔍 Code Review Process

1. PR is submitted
2. Maintainer reviews code
3. Feedback is provided (if needed)
4. Changes are requested or PR is approved
5. PR is merged

## 🚫 What NOT to Include

- API keys or tokens
- Database files with real data
- Personal information
- Passwords or credentials
- Large binary files
- Unrelated features

## 📋 Checklist

Before submitting your PR, make sure:

- [ ] Code follows PEP 8 style guide
- [ ] All functions have docstrings
- [ ] No sensitive data is included
- [ ] Feature has been tested locally
- [ ] README updated (if needed)
- [ ] No merge conflicts
- [ ] Commit messages are clear

## 🎯 Areas Where We Need Help

- **Documentation**: Improve existing docs, add tutorials
- **Testing**: Write unit tests, integration tests
- **Features**: Implement roadmap features
- **Bug Fixes**: Fix reported issues
- **Translations**: Add multi-language support
- **Performance**: Optimize slow operations
- **UI/UX**: Improve bot user experience

## 💡 Ideas for Contributions

### Easy (Good First Issue)
- Fix typos in documentation
- Add code comments
- Improve error messages
- Add input validation

### Medium
- Add new search sources
- Improve admin panel UI
- Add export functionality
- Implement caching improvements

### Advanced
- Add machine learning for fraud detection
- Create Docker deployment
- Add API endpoints
- Implement queue system for bulk searches

## 📞 Questions?

- Open a [GitHub Issue](https://github.com/affifuddin-hazam/PenipuMY/issues)
- Join our [Telegram Support Group](https://t.me/PenipuMYGroup)
- Email: support@penipu.my

## 🙏 Recognition

Contributors will be:
- Listed in README.md
- Mentioned in release notes
- Given credit in commit history

Thank you for making this project better!
