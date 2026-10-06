import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { PasswordInput } from "./PasswordInput";

describe("PasswordInput", () => {
  it("masks the value by default and reveals it on toggle click", async () => {
    const user = userEvent.setup();
    render(<PasswordInput value="secret123" onChange={() => {}} />);

    const input = screen.getByDisplayValue("secret123") as HTMLInputElement;
    expect(input.type).toBe("password");

    await user.click(screen.getByLabelText("Показать пароль"));
    expect(input.type).toBe("text");

    await user.click(screen.getByLabelText("Скрыть пароль"));
    expect(input.type).toBe("password");
  });
});
