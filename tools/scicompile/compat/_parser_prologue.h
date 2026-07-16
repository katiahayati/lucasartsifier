// See CMake/BUILD_NOTES: the SCI parser-combinator headers are template-heavy
// and, under MSVC's non-conformant two-phase lookup, resolved sci:: / std:: /
// parser-global names at instantiation. GCC resolves non-dependent names at
// definition, so we establish the expected context first.
#pragma once
#include "ScriptOM.h"     // full sci::Comment / CommentType / SyntaxNode / *Value defs
// Parser globals referenced inside templates before their in-file declaration:
int charToI(char ch);
extern char const errIntegerTooLarge[];
extern char const errIntegerTooSmall[];
using namespace sci;
using namespace std;
