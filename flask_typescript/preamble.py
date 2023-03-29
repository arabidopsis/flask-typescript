from __future__ import annotations


PREAMBLE = """
export type ValidationError = {
    loc: string[]
    msg: string
    type: string
}[]

export type Result<T> =
    | { success: true, result: T }
    | { success: false, error: ValidationError }
"""
