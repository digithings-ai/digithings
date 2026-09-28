"use client"

/**
 * Form — a thin presentational wrapper over the K1 `Field` and the kit inputs,
 * added in #4306 batch K2. This is deliberately **not** shadcn's
 * react-hook-form-bound Form: the repo carries no form-library dependency
 * (`react-hook-form` is not installed), so this part owns no state, no
 * validation and no submit. It supplies the `<form>` root with the canon's
 * vertical rhythm, a `FormField` façade over `Field` (label + hint/error +
 * accessible wiring, already meshed), and a `FormActions` footer row. Callers
 * keep owning the values and the submit handler.
 */
import type { ComponentProps } from "react"

import { cn } from "../lib/utils"
import { Field, type FieldProps } from "./field"

function Form({ className, ...props }: ComponentProps<"form">) {
  return <form data-slot="form" className={cn("grid gap-[1rem]", className)} {...props} />
}

function FormField({ className, ...props }: FieldProps) {
  return <Field className={cn("min-w-0", className)} {...props} />
}

function FormActions({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      data-slot="form-actions"
      className={cn("flex flex-wrap items-center gap-[0.6rem]", className)}
      {...props}
    />
  )
}

export { Form, FormField, FormActions }
